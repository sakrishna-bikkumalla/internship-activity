import csv
import http.client
import io
import os
import time
from urllib.parse import urlparse

import requests
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project
from gitlab_utils.client import GitLabClient  # For user APIs only

# Dependency availability
try:
    import pandas as pd  # noqa: F401

    PANDAS_AVAILABLE = True
except Exception:
    PANDAS_AVAILABLE = False

# Excel engine availability
try:
    import openpyxl  # noqa: F401

    OPENPYXL_AVAILABLE = True
except Exception:
    OPENPYXL_AVAILABLE = False

try:
    import xlsxwriter  # noqa: F401

    XLSXWRITER_AVAILABLE = True
except Exception:
    XLSXWRITER_AVAILABLE = False

# Provide a helpful pip suggestion
if not PANDAS_AVAILABLE:
    # pandas missing — suggest installing pandas and an engine
    if not (OPENPYXL_AVAILABLE or XLSXWRITER_AVAILABLE):
        EXCEL_PIP_SUGGEST = "pip install pandas openpyxl"
    else:
        EXCEL_PIP_SUGGEST = "pip install pandas"
else:
    # pandas present, engines may be missing
    if not (OPENPYXL_AVAILABLE or XLSXWRITER_AVAILABLE):
        EXCEL_PIP_SUGGEST = "pip install openpyxl"
    else:
        EXCEL_PIP_SUGGEST = "pip install pandas"


# --- Optimize: Cache file reads ---
@st.cache_data(ttl=60)
def read_file_content(_project, file_path, ref):
    try:
        file = _project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None


# --- Network helper: GitLab get with retries ---
def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    """Attempt to fetch a project from GitLab with retries on transient network errors.

    Returns the project object on success or raises the last exception on failure.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return gl_client.projects.get(
                int(path_or_id) if str(path_or_id).isdigit() else path_or_id
            )
        except GitlabGetError as e:
            # If it's a 404-like error (project not found), re-raise immediately
            last_exc = e
            # GitlabGetError can represent many server-side problems; treat as final for not-found
            if getattr(e, "response", None) is not None and e.response.status_code == 404:
                raise
            if attempt == retries:
                raise
        except (
            ConnectionResetError,
            ConnectionAbortedError,
            requests.exceptions.RequestException,
            OSError,
            http.client.RemoteDisconnected,
        ) as e:
            last_exc = e
            if attempt == retries:
                raise
            sleep_for = backoff * (2 ** (attempt - 1))
            time.sleep(sleep_for)
    # If loop exits without returning, raise the last exception
    if last_exc:
        raise last_exc


# --- Compliance Logic ---
def check_vscode_settings(project, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return "settings.json" in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_vscode_file_exists(project, filename, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return filename.lower() in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_license_content(project, branch="main"):
    """Check if license is AGPLv3, other GNU, or invalid using official headers and dates"""
    content = read_file_content(project, "LICENSE", branch) or read_file_content(
        project, "LICENSE.md", branch
    )
    if not content:
        return "not_found"

    # Normalize: lowercase, single spaces
    cleaned = " ".join(content.strip().split()).lower()

    # --- Check for AGPLv3 using official header and date ---
    has_affero = "affero" in cleaned
    has_gpl = "general public license" in cleaned
    has_version_3 = "version 3" in cleaned or "v3" in cleaned or "3.0" in cleaned
    has_correct_agpl_date = "19 november 2007" in cleaned

    # ✅ Only if ALL AGPLv3 criteria match
    if has_affero and has_gpl and has_version_3 and has_correct_agpl_date:
        return "valid"  # ✅ True AGPLv3

    # --- Check for GPLv3 using its official date ---
    has_correct_gplv3_date = "29 june 2007" in cleaned
    is_gplv3 = has_gpl and has_version_3 and has_correct_gplv3_date and not has_affero

    # --- Check for LGPLv3 ---
    has_lgpl = "lgpl" in cleaned or "lesser general public license" in cleaned
    has_correct_lgpl_date = "29 june 2007" in cleaned  # LGPLv3 also uses same date
    is_lgplv3 = has_lgpl and has_version_3 and has_correct_lgpl_date

    # 🟡 Other GNU licenses (GPLv3, LGPLv3)
    if is_gplv3 or is_lgplv3:
        return "gnu_other"

    # --- Check for other GNU licenses without version 3 ---
    has_gnu = "gnu" in cleaned
    has_gpl_v2 = "version 2" in cleaned or "v2" in cleaned or "2.0" in cleaned
    has_gpl_general = has_gpl and not has_affero  # Any GPL that isn't AGPL

    if (
        (has_gnu and has_gpl_general and (has_version_3 or has_gpl_v2))
        or (has_lgpl and (has_version_3 or has_gpl_v2))
        or (has_gpl_general and (has_version_3 or has_gpl_v2))
    ):
        return "gnu_other"

    # --- Common non-GNU licenses ---
    non_gnu_licenses = [
        "mit license",
        "apache license",
        "apache 2.0",
        "bsd license",
        "unlicense",
        "zlib",
        "isc license",
        "mozilla public license",
        "eclipse public license",
        "creative commons",
    ]

    if any(phrase in cleaned for phrase in non_gnu_licenses):
        return "invalid"

    # --- Fallback: generic license detection ---
    if "license" in cleaned and "copyright" in cleaned:
        # If it mentions GNU/GPL but didn't match above (e.g., malformed)
        if has_gnu or has_gpl or has_lgpl:
            return "gnu_other"
        return "invalid"

    return "invalid"


def check_vscode_settings_content(project, branch="main"):
    """Check only if .vscode/settings.json exists"""
    content = read_file_content(project, ".vscode/settings.json", branch)
    return {"exists": content is not None}


def check_extensions_json_for_ruff(project, branch="main"):
    """Check if Ruff is recommended in .vscode/extensions.json"""
    content = read_file_content(project, ".vscode/extensions.json", branch)
    if not content:
        return False
    try:
        import json

        config = json.loads(content)
        recommendations = config.get("recommendations", [])
        return "charliermarsh.ruff" in recommendations or any(
            "ruff" in ext.lower() for ext in recommendations
        )
    except Exception:
        return False


def list_markdown_files_in_folder(project, folder_path, branch="main"):
    try:
        items = project.repository_tree(path=folder_path, ref=branch)
        return [item["name"] for item in items if item["name"].lower().endswith(".md")]
    except Exception:
        return []


def check_templates_presence(project, branch="main"):
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }
    try:
        items = project.repository_tree(path=".gitlab/issue_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["issue_templates_folder"] = True
            result["issue_template_files"] = md_files
    except Exception:
        pass
    try:
        items = project.repository_tree(path=".gitlab/merge_request_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["merge_request_templates_folder"] = True
            result["merge_request_template_files"] = md_files
    except Exception:
        pass
    return result


def check_project_compliance(project, branch=None):
    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md"],
        # LICENSE handled separately
    }
    report = {}
    try:
        branch = branch or getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        # Check required files
        for label, variants in required_files.items():
            report[label] = any(variant.lower() in filenames for variant in variants)

        # README detection: check existence and content quality
        readme_present = any(n for n in filenames if n.startswith("readme"))
        report["README.md"] = readme_present
        if readme_present:
            # Try common README filename variants
            content = read_file_content(project, "README.md", branch) or read_file_content(
                project, "README", branch
            )
            if not content or not content.strip():
                report["readme_status"] = "empty"
                report["readme_sections"] = []
                report["readme_needs_improvement"] = True
                report["readme_quality_score"] = 0
            else:
                lc = content.lower()
                expected_sections = [
                    "installation",
                    "usage",
                    "getting started",
                    "setup",
                    "license",
                    "contributing",
                    "example",
                    "quick start",
                    "features",
                ]
                found_sections = [s for s in expected_sections if s in lc]
                report["readme_status"] = "present"
                report["readme_sections"] = found_sections
                report["readme_needs_improvement"] = (
                    len(found_sections) < 3 or len(content.strip()) < 150
                )
                # Calculate README quality score
                report["readme_quality_score"] = calculate_readme_quality_score(content)

                # Check section order by tracking their positions
                section_positions = {}
                for section in expected_sections:
                    pos = lc.find(section)
                    if pos != -1:
                        section_positions[section] = pos

                # Check if sections are in logical order (installation before usage, etc.)
                # Define recommended order
                recommended_order = [
                    "installation",
                    "setup",
                    "getting started",
                    "usage",
                    "features",
                    "example",
                    "quick start",
                    "contributing",
                    "license",
                ]
                found_ordered = [s for s in recommended_order if s in section_positions]
                positions_list = [section_positions[s] for s in found_ordered]

                # Check if positions are in ascending order
                is_ordered = all(
                    positions_list[i] < positions_list[i + 1]
                    for i in range(len(positions_list) - 1)
                )
                report["readme_section_order_correct"] = is_ordered or len(found_ordered) <= 1
                report["readme_section_positions"] = section_positions
        else:
            report["readme_status"] = "missing"
            report["readme_sections"] = []
            report["readme_needs_improvement"] = True
            report["readme_quality_score"] = 0

        # Check LICENSE existence and validity
        license_variants = ["LICENSE", "LICENSE.md"]
        report["LICENSE"] = any(variant.lower() in filenames for variant in license_variants)

        if report["LICENSE"]:
            license_status = check_license_content(project, branch)
        else:
            license_status = "not_found"

        report["license_valid"] = license_status == "valid"
        report["license_status"] = license_status

        # Other files
        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames
        report["uv_lock_exists"] = "uv.lock" in filenames  # ✅ New check

        # VSCode config
        report["vscode_settings"] = check_vscode_settings(project, branch)
        vscode_content = check_vscode_settings_content(project, branch)
        report["vscode_config_exists"] = vscode_content["exists"]

        # ✅ Ruff check in extensions.json
        report["vscode_ruff_in_extensions"] = check_extensions_json_for_ruff(project, branch)

        # Other VSCode files
        report["vscode_extensions_exists"] = check_vscode_file_exists(
            project, "extensions.json", branch
        )
        report["vscode_launch_exists"] = check_vscode_file_exists(project, "launch.json", branch)
        report["vscode_tasks_exists"] = check_vscode_file_exists(project, "tasks.json", branch)

        # Templates
        template_details = check_templates_presence(project, branch)
        report.update(template_details)

        # Metadata
        report["description_present"] = bool(project.description and project.description.strip())
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report


# Patch Project class
def patch_gitlab_project():
    Project.check_compliance = lambda self, branch=None: check_project_compliance(self, branch)


patch_gitlab_project()


# --- File listing and classification helpers ---
def list_all_files(project, branch="main"):
    """Return list of file paths (blobs) in the repository (recursive)."""
    try:
        # Try with common params
        items = project.repository_tree(ref=branch, recursive=True, all=True)
    except TypeError:
        # Fallback if 'all' not supported by the API client
        items = project.repository_tree(ref=branch, recursive=True)
    files = [item.get("path") for item in items if item.get("type") == "blob"]
    return files


def classify_repository_files(file_paths):
    """Classify files into categories and detect language files."""
    res = {
        "common_requirements": [],
        "project_files": [],
        "tech_files": [],
        "python_files": [],
        "js_files": [],
        "java_files": [],
        "go_files": [],
        "rust_files": [],
        "csharp_files": [],
        "detected_languages": [],
    }
    for p in file_paths or []:
        lp = p.lower()
        filename = os.path.basename(lp)

        # Common requirement files
        if filename in {
            "requirements.txt",
            "requirements-dev.txt",
            "pipfile",
            "pipfile.lock",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            "poetry.lock",
            "setup.py",
            "setup.cfg",
            "pom.xml",
            "gradle.properties",
            "go.mod",
            "go.sum",
            "cargo.toml",
            "cargo.lock",
            "csproj",
            ".csproj",
        }:
            res["common_requirements"].append(p)

        # Project files
        if (
            filename
            in {
                "readme.md",
                "contributing.md",
                "changelog",
                "changelog.md",
                "license",
                "license.md",
            }
            or lp.startswith("docs/")
            or lp.startswith("src/")
            or lp.startswith("tests/")
        ):
            res["project_files"].append(p)

        # Tech / tooling files
        if (
            filename
            in {
                "dockerfile",
                "docker-compose.yml",
                ".gitlab-ci.yml",
                ".gitignore",
                "makefile",
                "tox.ini",
                ".pre-commit-config.yaml",
                ".editorconfig",
                ".eslintrc",
                ".eslintrc.json",
            }
            or lp.startswith(".vscode/")
            or lp.startswith(".github/")
        ):
            res["tech_files"].append(p)

        # Language-specific detection
        if lp.endswith(".py"):
            res["python_files"].append(p)
            if "Python" not in res["detected_languages"]:
                res["detected_languages"].append("Python")
        if lp.endswith((".js", ".jsx", ".ts", ".tsx")):
            res["js_files"].append(p)
            if "JavaScript/TypeScript" not in res["detected_languages"]:
                res["detected_languages"].append("JavaScript/TypeScript")
        if lp.endswith(".java"):
            res["java_files"].append(p)
            if "Java" not in res["detected_languages"]:
                res["detected_languages"].append("Java")
        if lp.endswith(".go"):
            res["go_files"].append(p)
            if "Go" not in res["detected_languages"]:
                res["detected_languages"].append("Go")
        if lp.endswith(".rs"):
            res["rust_files"].append(p)
            if "Rust" not in res["detected_languages"]:
                res["detected_languages"].append("Rust")
        if lp.endswith((".cs", ".csproj")):
            res["csharp_files"].append(p)
            if "C#" not in res["detected_languages"]:
                res["detected_languages"].append("C#")

    # Deduplicate lists
    for k in res:
        if isinstance(res[k], list):
            res[k] = sorted(dict.fromkeys(res[k]))
    return res


def calculate_readme_quality_score(content):
    """Calculate README quality score (0-100) based on content analysis."""
    if not content or not content.strip():
        return 0

    lc = content.lower()
    score = 0

    # Content length bonus (max 15 points)
    content_len = len(content.strip())
    if content_len > 500:
        score += 15
    elif content_len > 300:
        score += 10
    elif content_len > 100:
        score += 5

    # Section presence checks (max 60 points)
    essential_sections = {
        "installation": 10,
        "usage": 10,
        "getting started": 10,
        "setup": 5,
        "features": 10,
        "contributing": 5,
        "license": 10,
    }
    for section, points in essential_sections.items():
        if section in lc:
            score += points

    # Code examples/blocks bonus (max 10 points)
    if "```" in content:
        score += 10
    elif "`" in content:
        score += 5

    # Links and references bonus (max 5 points)
    if "http" in lc or "[" in content:
        score += 5

    # Project structure/clarity (max 10 points)
    heading_count = content.count("#")
    if heading_count >= 5:
        score += 10
    elif heading_count >= 3:
        score += 5

    return min(score, 100)  # Cap at 100


def render_readme_quality_progress_bar(score):
    """Render a visual progress bar for README quality score."""
    # Determine color based on score
    if score >= 85:
        color = "#00d084"  # Green
        label = "Excellent"
    elif score >= 70:
        color = "#a3e635"  # Yellow-green
        label = "Good"
    elif score >= 50:
        color = "#fbbf24"  # Amber
        label = "Fair"
    elif score >= 25:
        color = "#f97316"  # Orange
        label = "Poor"
    else:
        color = "#ef4444"  # Red
        label = "Very Poor"

    # Create custom progress bar HTML
    progress_html = f"""
    <div style="margin: 10px 0;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <span style="font-weight: bold;">README Quality Score</span>
            <span style="font-weight: bold; color: {color};">{score}/100 ({label})</span>
        </div>
        <div style="width: 100%; height: 25px; background-color: #e5e7eb; border-radius: 5px; overflow: hidden; border: 1px solid #d1d5db;">
            <div style="height: 100%; width: {score}%; background-color: {color}; transition: width 0.3s ease;"></div>
        </div>
    </div>
    """
    st.markdown(progress_html, unsafe_allow_html=True)


def reports_to_csv(rows):
    """Convert a list of per-project summary dicts into CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "project_id",
        "path",
        "branch",
        "python_count",
        "js_count",
        "common_requirements",
        "project_files",
        "tech_files",
        "license_status",
        "license_valid",
        "readme_status",
        "readme_notes",
    ]
    writer.writerow(headers)
    for r in rows:
        writer.writerow(
            [
                r.get("project_id"),
                r.get("path"),
                r.get("branch"),
                r.get("python_count"),
                r.get("js_count"),
                ";".join([os.path.basename(p) for p in r.get("common_requirements", [])]),
                ";".join([os.path.basename(p) for p in r.get("project_files", [])]),
                ";".join([os.path.basename(p) for p in r.get("tech_files", [])]),
                r.get("license_status"),
                r.get("license_valid"),
                r.get("readme_status"),
                r.get("readme_notes"),
            ]
        )
    return output.getvalue()


def reports_to_excel(rows):
    """Return Excel bytes for rows using pandas. Chooses an available engine (openpyxl or xlsxwriter).

    Raises RuntimeError with a helpful message if pandas or an Excel engine is unavailable.
    """
    try:
        from io import BytesIO

        import pandas as pd
    except Exception as e:
        raise RuntimeError(
            "pandas is required to generate Excel files. Install with: pip install pandas openpyxl"
        ) from e

    df_rows = []
    for r in rows:
        df_rows.append(
            {
                "project_id": r.get("project_id"),
                "path": r.get("path"),
                "branch": r.get("branch"),
                "python_count": r.get("python_count"),
                "js_count": r.get("js_count"),
                "common_requirements": ";".join(
                    [os.path.basename(p) for p in r.get("common_requirements", [])]
                ),
                "project_files": ";".join(
                    [os.path.basename(p) for p in r.get("project_files", [])]
                ),
                "tech_files": ";".join([os.path.basename(p) for p in r.get("tech_files", [])]),
                "license_status": r.get("license_status"),
                "license_valid": r.get("license_valid"),
                "readme_status": r.get("readme_status"),
                "readme_notes": ";".join(
                    r.get("readme_notes", [])
                    if isinstance(r.get("readme_notes"), list)
                    else ([r.get("readme_notes")] if r.get("readme_notes") else [])
                ),
            }
        )
    df = pd.DataFrame(df_rows)

    # Choose an available engine
    engine = None
    if OPENPYXL_AVAILABLE:
        engine = "openpyxl"
    elif XLSXWRITER_AVAILABLE:
        engine = "xlsxwriter"

    if engine is None:
        raise RuntimeError(
            "No Excel writer available (openpyxl or xlsxwriter). Install with: pip install openpyxl or pip install xlsxwriter"
        )

    buf = BytesIO()
    try:
        df.to_excel(buf, index=False, engine=engine, sheet_name="Report")
        buf.seek(0)  # Reset buffer position to beginning before reading
    except Exception as e:
        raise RuntimeError(f"Failed to generate Excel file using engine '{engine}': {e}") from e

    return buf.getvalue()


def extract_path_from_url(input_str):
    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


def get_user_from_token(base_url, token):
    try:
        headers = {"PRIVATE-TOKEN": token}
        url = f"{base_url}/api/v4/user"
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return f"Error validating token: {e}"


def get_user_groups_by_token(base_url, token):
    """
    Get groups of the AUTHENTICATED user.
    Works even when /users/:id/groups is disabled.
    """
    try:
        headers = {"PRIVATE-TOKEN": token}

        api_base = base_url.rstrip("/")
        if api_base.endswith("/api/v4"):
            url = f"{api_base}/groups?membership=true"
        else:
            url = f"{api_base}/api/v4/groups?membership=true"

        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    except Exception as e:
        return f"Error fetching groups: {e}"


# --- Suggestions Helper ---
def get_suggestions_for_missing_items(report):
    suggestion_list = [
        (
            "README.md",
            "README.md missing",
            "Add a `README.md` file at the root of the repository with setup and usage instructions.",
        ),
        (
            "CONTRIBUTING.md",
            "CONTRIBUTING.md missing",
            "Add a `CONTRIBUTING.md` file to guide collaborators on how to contribute to the project.",
        ),
        (
            "CHANGELOG",
            "CHANGELOG missing",
            "Maintain a `CHANGELOG.md` file to record changes across versions for better transparency.",
        ),
        (
            "LICENSE",
            "LICENSE missing",
            "Include an `AGPLv3 LICENSE` file to define the legal usage of your project.",
        ),
        (
            "license_valid",
            "LICENSE is not AGPLv3",
            "Ensure the license is AGPLv3. Replace MIT/Apache with AGPLv3 for compliance.",
        ),
        (
            "issue_templates_folder",
            "Issue templates folder missing",
            "Create `.gitlab/issue_templates/` and add `.md` templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
        ),
        (
            "merge_request_templates_folder",
            "Merge request templates folder missing",
            "Create `.gitlab/merge_request_templates/` and add MR templates like `Bug.md`, `Documentation.md`, or `Default.md`.",
        ),
        (
            ".gitignore",
            ".gitignore missing",
            "Add a `.gitignore` file to specify untracked files to ignore in your repository.",
        ),
        (
            "pyproject.toml",
            "pyproject.toml missing",
            "Add a `pyproject.toml` file to declare Python build system requirements and project metadata.",
        ),
        (
            "vscode_settings",
            ".vscode/settings.json missing",
            "Add a `.vscode/settings.json` file to configure editor settings for consistency across contributors.",
        ),
        (
            "vscode_ruff_in_extensions",
            "Ruff not in .vscode/extensions.json",
            "Add `charliermarsh.ruff` to `.vscode/extensions.json` under `recommendations` to enforce Ruff linter usage.",
        ),
        (
            "vscode_extensions_exists",
            ".vscode/extensions.json missing",
            "Add a `.vscode/extensions.json` file to configure recommended VSCode extensions.",
        ),
        (
            "vscode_launch_exists",
            ".vscode/launch.json missing",
            "Add a `.vscode/launch.json` file to configure debug launch profiles in VSCode.",
        ),
        (
            "vscode_tasks_exists",
            ".vscode/tasks.json missing",
            "Add a `.vscode/tasks.json` file to define custom tasks for build, lint, or deployment.",
        ),
        (
            "description_present",
            "Project description missing",
            "Provide a meaningful project description in GitLab settings.",
        ),
        (
            "tags_present",
            "Project tags missing",
            "Tag your project releases for version control and clarity.",
        ),
        (
            "uv_lock_exists",
            "uv.lock missing",
            "Run `uv lock` to generate `uv.lock` for dependency locking. Commit this file to ensure reproducible environments.",
        ),
    ]

    image_map = {
        "README.md": "Readme.png",
        "CONTRIBUTING.md": "Contributing.png",
        "CHANGELOG": "Changelog.png",
        "LICENSE": "license-example.png",
        "license_valid": "license-wrong.png",
        "issue_templates_folder": "issue_template_files.png",
        "merge_request_templates_folder": "merge_request_files.png",
        ".gitignore": "gitignore.png",
        "pyproject.toml": "pyproject-toml.png",
        "vscode_settings": "vscode-settings.png",
        "vscode_ruff_in_extensions": "vscode-extensions.png",
        "vscode_extensions_exists": "vscode-extensions.png",
        "vscode_launch_exists": "vscode-launch.png",
        "vscode_tasks_exists": "vscode-tasks.png",
        "description_present": "project-description.png",
        "tags_present": "Tags.png",
        "uv_lock_exists": "uvlock.png",
    }

    st.subheader("📌 Suggestions for Missing Items")
    show_files_image = not report.get("issue_templates_folder", False) or not report.get(
        "merge_request_templates_folder", False
    )
    files_image_shown = False

    for key, display_name, suggestion_text in suggestion_list:
        if not report.get(key, True):  # If missing
            if (
                key in ["issue_templates_folder", "merge_request_templates_folder"]
                and show_files_image
                and not files_image_shown
            ):
                try:
                    st.image(
                        "assets/files.png",
                        caption="Recommended file structure inside `.gitlab/` directory",
                        width=500,
                    )
                    files_image_shown = True
                except Exception:
                    st.warning("Could not load: assets/files.png")
            st.markdown(f"❌ **{display_name}** — {suggestion_text}")
            img_file = image_map.get(key)
            if img_file:
                try:
                    st.image(f"assets/{img_file}", width=400)
                except Exception:
                    pass

    # --- Additional README suggestions ---
    readme_status = report.get("readme_status")
    if readme_status == "missing":
        st.markdown(
            "❌ **README missing** — Add a `README.md` at the repository root. Include: Installation, Usage, License, and Contribution guidelines."
        )
        st.markdown(
            """**Quick README template:**

```
# Project Title

Short description.

## Installation
Instructions

## Usage
Examples

## Contributing
How to contribute

## License
AGPLv3
```
"""
        )
    elif readme_status == "empty":
        st.markdown("❌ **README is empty** — Add meaningful content (see template above).")
    elif report.get("readme_needs_improvement"):
        missing = []
        expected_sections = [
            "installation",
            "usage",
            "getting started",
            "setup",
            "license",
            "contributing",
            "example",
            "quick start",
            "features",
        ]
        found = report.get("readme_sections", []) or []
        for s in expected_sections:
            if s not in found:
                missing.append(s)
        if missing:
            st.markdown(
                f"🟡 **README needs improvement** — Consider adding sections: {', '.join(missing[:5])}"
            )
            st.markdown(
                "**Suggestion**: Add Installation/Usage/License/Contributing sections and include examples or quick start steps."
            )
        else:
            st.markdown(
                "✅ **README looks good**, but consider expanding examples or usage instructions if short."
            )


# --- Project compliance rendering helper ---
def render_project_compliance_ui(report, project=None, branch=None, classification=None):
    """Render the compliance summary UI for a project (reusable for single and batch views)."""
    st.markdown("### 📋 Compliance Summary by Category")
    categories = {
        "1. 📄 Project Metadata": {
            "description_present": "Project Description",
            "tags_present": "Tags",
        },
        "2. 📚 Project Documentation": {
            "README.md": "README.md",
            "CONTRIBUTING.md": "CONTRIBUTING.md",
            "CHANGELOG": "CHANGELOG / CHANGELOG.md",
            "LICENSE": "LICENSE / LICENSE.md",
            "license_valid": "LICENSE should be AGPLv3",
            "issue_templates_folder": "Issue Templates Folder (.gitlab/issue_templates)",
            "issue_template_files": "Issue Template Files",
            "merge_request_templates_folder": "Merge Request Templates Folder (.gitlab/merge_request_templates)",
            "merge_request_template_files": "Merge Request Template Files",
            "readme_status": "README status",
        },
        "3. ⚙️ Project Configuration": {
            ".gitignore": ".gitignore",
            "pyproject.toml": "pyproject.toml",
            "uv_lock_exists": "uv.lock",
        },
        "4. 🖥️ IDE Setup": {
            "vscode_settings": ".vscode/settings.json",
            "vscode_ruff_in_extensions": "Ruff in .vscode/extensions.json",
            "vscode_extensions_exists": ".vscode/extensions.json",
            "vscode_launch_exists": ".vscode/launch.json",
            "vscode_tasks_exists": ".vscode/tasks.json",
        },
        "5. 🗂️ File Categories": {
            "python_count": "Python files",
            "js_count": "JS/TS files",
            "java_count": "Java files",
            "go_count": "Go files",
            "rust_count": "Rust files",
            "csharp_count": "C# files",
            "detected_languages_list": "Detected Languages",
            "common_requirements_list": "Common requirement files",
            "project_files_list": "Project files",
            "tech_files_list": "Tech / tooling files",
        },
    }

    all_passed = True
    for category_title, items in categories.items():
        st.markdown(
            f"<h4 style='font-size: 1.3em; font-weight: bold;'>{category_title}</h4>",
            unsafe_allow_html=True,
        )
        with st.expander("Click to view details", expanded=False):
            for key, display_name in items.items():
                status = report.get(key, False)

                if isinstance(status, list):
                    count = len(status)
                    emoji = "✅" if count > 0 else "❌"
                    st.markdown(f"{emoji} **{display_name}**: {count} file(s)")
                    if count > 0:
                        with st.expander("Show files", expanded=False):
                            for p in sorted(status):
                                st.markdown(f"- `{os.path.basename(p)}`")
                    else:
                        all_passed = False

                elif key == "license_valid":
                    license_status = report.get("license_status")
                    if license_status == "valid":
                        st.markdown("✅ **LICENSE is AGPLv3**")
                    elif license_status == "gnu_other":
                        st.markdown(
                            "🟠 **LICENSE should be AGPLv3** — GNU license found (e.g., GPLv3/LGPLv3) but not AGPLv3"
                        )
                        all_passed = False
                    else:
                        st.markdown(
                            "❌ **LICENSE should be AGPLv3** — License is non-GNU (e.g., MIT/Apache) or missing"
                        )
                        all_passed = False

                elif key == "readme_status":
                    rstatus = report.get("readme_status")
                    if rstatus == "present":
                        st.markdown("✅ **README present**")
                        # Show README quality score if available
                        readme_score = report.get("readme_quality_score")
                        if readme_score is not None:
                            render_readme_quality_progress_bar(readme_score)
                    elif rstatus == "empty":
                        st.markdown("❌ **README is empty**")
                        all_passed = False
                    else:
                        st.markdown("❌ **README missing**")
                        all_passed = False

                elif key in {
                    "python_count",
                    "js_count",
                    "java_count",
                    "go_count",
                    "rust_count",
                    "csharp_count",
                }:
                    st.markdown(f"**{display_name}**: {report.get(key, 0)}")

                elif key == "detected_languages_list":
                    langs = report.get(key, [])
                    if langs:
                        st.markdown(f"✅ **Detected Languages**: {', '.join(langs)}")
                    else:
                        st.markdown("❌ **Detected Languages**: None")

                else:
                    emoji = "✅" if status else "❌"
                    st.markdown(f"{emoji} **{display_name}**")
                    if not status:
                        all_passed = False

    if all_passed:
        st.success("🎉 **All Set!** This project meets all compliance requirements.")
    else:
        get_suggestions_for_missing_items(report)


# --- VSCode & pyproject.toml Documentation Markdown ---
def render_vscode_and_pyproject_docs():
    st.markdown(
        """
### 🛠️ Documentation for `.vscode` Configuration Files and `pyproject.toml`
These files help maintain consistent development environment and build configurations across the team.
- [`.vscode/launch.json`](https://code.visualstudio.com/docs/editor/debugging#_launch-configurations)
  Defines debug launch profiles for running and debugging the project inside VSCode.
- [`.vscode/extensions.json`](https://code.visualstudio.com/docs/editor/extension-marketplace#_recommended-extensions)
  Lists recommended VSCode extensions to install for efficient coding and linting.
- [`.vscode/settings.json`](https://code.visualstudio.com/docs/getstarted/settings)
  Contains workspace-specific editor settings such as Python interpreter path, linters (e.g., Ruff), and environment management (`uv`).
- [`.vscode/tasks.json`](https://code.visualstudio.com/docs/editor/tasks)
  Defines custom tasks to automate build, test, lint, or deployment commands within VS Code.
- [`pyproject.toml`](https://peps.python.org/pep-0518/)
  Configuration for Python project build system, dependencies, and packaging metadata. Ensures reproducible builds and integration with tools like Poetry or Flit.
        """
    )


# --------- Main Streamlit App ---------
load_dotenv()
TOKEN = st.secrets.get("GITLAB_TOKEN") or os.getenv("GITLAB_TOKEN")
URL = st.secrets.get("GITLAB_URL") or os.getenv("GITLAB_URL")
if not TOKEN or not URL:
    st.error("❌ GITLAB_TOKEN or GITLAB_URL not found. Please set them in secrets or .env.")
    st.stop()

client = GitLabClient(base_url=URL, private_token=TOKEN)  # For user APIs
gl = Gitlab(URL, private_token=TOKEN)  # For project APIs

st.title("GitLab Tools")
# Show dependency note
if not PANDAS_AVAILABLE or not (OPENPYXL_AVAILABLE or XLSXWRITER_AVAILABLE):
    st.sidebar.warning(
        f"Excel exports require pandas + an Excel engine. Install with: {EXCEL_PIP_SUGGEST}"
    )

# Verification button for runtime check (useful after installing packages)
if st.sidebar.button("Verify Excel support"):
    try:
        ok_pandas = False
        try:
            import pandas as _pd  # noqa: F401

            ok_pandas = True
        except Exception:
            ok_pandas = False
        ok_openpyxl = False
        try:
            import openpyxl  # noqa: F401

            ok_openpyxl = True
        except Exception:
            ok_openpyxl = False
        ok_xlsxwriter = False
        try:
            import xlsxwriter  # noqa: F401

            ok_xlsxwriter = True
        except Exception:
            ok_xlsxwriter = False

        if ok_pandas and (ok_openpyxl or ok_xlsxwriter):
            st.sidebar.success("Excel support verified: pandas + engine available.")
        else:
            missing = []
            if not ok_pandas:
                missing.append("pandas")
            if not (ok_openpyxl or ok_xlsxwriter):
                missing.append("openpyxl or xlsxwriter")
            st.sidebar.error(f"Missing: {', '.join(missing)}. Install: {EXCEL_PIP_SUGGEST}")
    except Exception as e:
        st.sidebar.error(f"Error verifying support: {e}")

mode = st.sidebar.radio(
    "Select Mode",
    ["Check Project Compliance", "User Profile Overview"],
)
# --- MODE: Check Project Compliance ---
if mode == "Check Project Compliance":
    st.subheader("📊 Project Compliance Checker")
    project_input = st.text_input(
        "Enter project path, URL, or project ID",
        key="project_compliance_input",
        on_change=lambda: st.session_state.update(
            {"project_compliance_run": True, "project_compliance_triggered": True}
        ),
    )

    if st.session_state.get("project_compliance_run"):
        st.session_state["project_compliance_run"] = False
        input_str = project_input.strip()
        if not input_str:
            st.warning("Please enter a valid project path, URL or ID.")
            st.session_state["selected_project_id"] = None
            st.session_state["branches"] = []
        else:
            path_or_id = extract_path_from_url(input_str)
            is_id = path_or_id.isdigit()
            try:
                project = get_project_with_retries(gl, path_or_id)
                st.session_state["selected_project_id"] = project.id
                branches = get_project_branches(project)
                st.session_state["branches"] = branches
            except GitlabGetError:
                st.error(f"Project '{path_or_id}' not found.")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []
            except Exception as e:
                st.error(f"Unexpected error ({type(e).__name__}): {e}")
                st.info("Check GITLAB_URL, GITLAB_TOKEN, network connectivity, and proxy settings.")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []

    selected_project_id = st.session_state.get("selected_project_id")
    branches = st.session_state.get("branches") or []

    # --- Batch Mode: accept multiple projects ---
    st.markdown("---")
    st.subheader("🔁 Batch Mode: Multiple Projects")
    st.checkbox(
        "Enable batch mode: analyze multiple repositories at once", key="batch_mode_enabled"
    )
    if st.session_state.get("batch_mode_enabled"):
        batch_input = st.text_area(
            "Enter multiple project paths, URLs, or IDs (one per line)",
            key="batch_projects_input",
            placeholder="group/project or https://gitlab.com/group/project or 12345",
        )
        run_batch = st.button("Run Batch Compliance & File Analysis", key="run_batch_button")
        if run_batch:
            lines = [line.strip() for line in (batch_input or "").splitlines() if line.strip()]
            if not lines:
                st.warning(
                    "Please enter at least one project path, URL, or ID for batch processing."
                )
            else:
                rows = []
                full_results = []
                with st.spinner(f"Processing {len(lines)} project(s) ..."):
                    for line in lines:
                        path_or_id = extract_path_from_url(line)
                        is_id = path_or_id.isdigit()
                        try:
                            proj = get_project_with_retries(gl, path_or_id)
                        except Exception as e:
                            st.error(f"Project '{path_or_id}' not found: {e}")
                            rows.append(
                                {
                                    "project_id": None,
                                    "path": path_or_id,
                                    "branch": None,
                                    "python_count": 0,
                                    "js_count": 0,
                                    "common_requirements": [],
                                    "project_files": [],
                                    "tech_files": [],
                                    "license_status": None,
                                    "license_valid": False,
                                    "readme_status": "error",
                                    "readme_notes": str(e),
                                    "error": str(e),
                                }
                            )
                            continue

                        try:
                            branch = getattr(proj, "default_branch", "main")
                            report = check_project_compliance(proj, branch=branch)
                            files = list_all_files(proj, branch=branch)
                            classification = classify_repository_files(files)

                            rows.append(
                                {
                                    "project_id": proj.id,
                                    "path": proj.path_with_namespace,
                                    "branch": branch,
                                    "python_count": len(classification.get("python_files", [])),
                                    "js_count": len(classification.get("js_files", [])),
                                    "java_count": len(classification.get("java_files", [])),
                                    "go_count": len(classification.get("go_files", [])),
                                    "rust_count": len(classification.get("rust_files", [])),
                                    "csharp_count": len(classification.get("csharp_files", [])),
                                    "detected_languages": ", ".join(
                                        classification.get("detected_languages", [])
                                    ),
                                    "common_requirements": classification.get(
                                        "common_requirements", []
                                    ),
                                    "project_files": classification.get("project_files", []),
                                    "tech_files": classification.get("tech_files", []),
                                    "license_status": report.get("license_status"),
                                    "license_valid": report.get("license_valid"),
                                    "readme_status": report.get("readme_status"),
                                    "readme_quality_score": report.get("readme_quality_score", 0),
                                    "readme_notes": ";".join(report.get("readme_sections", [])),
                                }
                            )

                            full_results.append(
                                {
                                    "project": proj,
                                    "report": report,
                                    "classification": classification,
                                    "branch": branch,
                                }
                            )
                        except Exception as e:
                            # Catch unexpected per-project errors and continue
                            st.error(
                                f"Error processing project {proj.path_with_namespace if proj else path_or_id}: {e}"
                            )
                            rows.append(
                                {
                                    "project_id": proj.id if proj else None,
                                    "path": proj.path_with_namespace if proj else path_or_id,
                                    "branch": getattr(proj, "default_branch", None)
                                    if proj
                                    else None,
                                    "python_count": 0,
                                    "js_count": 0,
                                    "common_requirements": [],
                                    "project_files": [],
                                    "tech_files": [],
                                    "license_status": None,
                                    "license_valid": False,
                                    "readme_status": "error",
                                    "readme_notes": str(e),
                                    "error": str(e),
                                }
                            )
                if rows:
                    st.success(f"Processed {len(rows)} project(s)")

                    # Prepare a display table that shows file names (not Python list repr)
                    display_rows = []
                    for r in rows:
                        dr = dict(r)
                        for key in ["common_requirements", "project_files", "tech_files"]:
                            dr[key] = (
                                ", ".join([os.path.basename(p) for p in r.get(key, [])])
                                if r.get(key)
                                else ""
                            )
                        display_rows.append(dr)

                    st.dataframe(display_rows)

                    # Show detailed per-project breakdown (present as compliance checklist UI)
                    st.markdown("---")
                    st.subheader("Detailed per-project compliance reports")
                    for full in full_results:
                        proj = full.get("project")
                        rep = full.get("report")
                        clas = full.get("classification")
                        branch = full.get("branch")
                        with st.expander(
                            f"{proj.path_with_namespace} (ID: {proj.id})", expanded=False
                        ):
                            st.write(f"Branch: `{branch}`")
                            # Render the same compliance UI as the single project checker
                            render_project_compliance_ui(
                                rep, project=proj, branch=branch, classification=clas
                            )

                    try:
                        excel_bytes = reports_to_excel(rows)
                        st.download_button(
                            "Download Excel Report",
                            data=excel_bytes,
                            file_name="batch_compliance_report.xlsx",
                            mime="application/octet-stream",
                        )
                    except Exception as e:
                        # Show detailed error and provide an install suggestion
                        st.error(f"Could not create Excel report: {e}")
                        st.info(f"Tip: Install Excel writer support: {EXCEL_PIP_SUGGEST}")
                        csv_content = reports_to_csv(rows)
                        st.warning("Falling back to CSV export.")
                        st.download_button(
                            "Download CSV Report",
                            data=csv_content,
                            file_name="batch_compliance_report.csv",
                            mime="text/csv",
                        )

    st.markdown("---")

    if selected_project_id:
        try:
            project = get_project_with_retries(gl, selected_project_id)
            if not branches:
                branches = get_project_branches(project)
                st.session_state["branches"] = branches

            default_branch = getattr(project, "default_branch", "main")
            if default_branch in branches:
                default_idx = branches.index(default_branch)
            elif "main" in branches:
                default_idx = branches.index("main")
            else:
                default_idx = 0 if branches else None

            if branches:
                selected_branch = st.selectbox(
                    "Select branch for compliance check:",
                    branches,
                    index=default_idx if default_idx is not None else 0,
                    key="branch_selector",
                )
            else:
                selected_branch = default_branch
                st.warning("No branches found, will check default/main branch if possible.")

            run_check = st.button(
                "Run Compliance Check on Selected Branch", key="run_compliance_check"
            )
            run_automatic = len(branches) == 1 and (branches[0] == default_branch)

            if run_check or run_automatic:
                report = check_project_compliance(project=project, branch=selected_branch)

                # Classify repository files and include counts into report for display
                files_for_classify = list_all_files(project, branch=selected_branch)
                classification = classify_repository_files(files_for_classify)
                report["python_count"] = len(classification.get("python_files", []))
                report["js_count"] = len(classification.get("js_files", []))
                report["java_count"] = len(classification.get("java_files", []))
                report["go_count"] = len(classification.get("go_files", []))
                report["rust_count"] = len(classification.get("rust_files", []))
                report["csharp_count"] = len(classification.get("csharp_files", []))
                report["detected_languages_list"] = classification.get("detected_languages", [])
                report["common_requirements_list"] = classification.get("common_requirements", [])
                report["project_files_list"] = classification.get("project_files", [])
                report["tech_files_list"] = classification.get("tech_files", [])

                if "error" in report:
                    st.error(report["error"])
                else:
                    st.markdown("### 📋 Compliance Summary by Category")
                    categories = {
                        "1. 📄 Project Metadata": {
                            "description_present": "Project Description",
                            "tags_present": "Tags",
                        },
                        "2. 📚 Project Documentation": {
                            "README.md": "README.md",
                            "CONTRIBUTING.md": "CONTRIBUTING.md",
                            "CHANGELOG": "CHANGELOG / CHANGELOG.md",
                            "LICENSE": "LICENSE / LICENSE.md",
                            "license_valid": "LICENSE should be AGPLv3",
                            "issue_templates_folder": "Issue Templates Folder (.gitlab/issue_templates)",
                            "issue_template_files": "Issue Template Files",
                            "merge_request_templates_folder": "Merge Request Templates Folder (.gitlab/merge_request_templates)",
                            "merge_request_template_files": "Merge Request Template Files",
                            "readme_status": "README status",
                        },
                        "3. ⚙️ Project Configuration": {
                            ".gitignore": ".gitignore",
                            "pyproject.toml": "pyproject.toml",
                            "uv_lock_exists": "uv.lock",
                        },
                        "4. 🖥️ IDE Setup": {
                            "vscode_settings": ".vscode/settings.json",
                            "vscode_ruff_in_extensions": "Ruff in .vscode/extensions.json",
                            "vscode_extensions_exists": ".vscode/extensions.json",
                            "vscode_launch_exists": ".vscode/launch.json",
                            "vscode_tasks_exists": ".vscode/tasks.json",
                        },
                        "5. 🗂️ File Categories": {
                            "python_count": "Python files",
                            "js_count": "JS/TS files",
                            "java_count": "Java files",
                            "go_count": "Go files",
                            "rust_count": "Rust files",
                            "csharp_count": "C# files",
                            "detected_languages_list": "Detected Languages",
                            "common_requirements_list": "Common requirement files",
                            "project_files_list": "Project files",
                            "tech_files_list": "Tech / tooling files",
                        },
                    }
                    all_passed = True
                    for category_title, items in categories.items():
                        st.markdown(
                            f"<h4 style='font-size: 1.3em; font-weight: bold;'>{category_title}</h4>",
                            unsafe_allow_html=True,
                        )
                        with st.expander("Click to view details", expanded=True):
                            for key, display_name in items.items():
                                status = report.get(key, False)

                                if isinstance(status, list):
                                    count = len(status)
                                    emoji = "✅" if count > 0 else "❌"
                                    listed = ", ".join(sorted(status)) if status else "None"
                                    st.markdown(
                                        f"{emoji} **{display_name}**: {count} file(s) ({listed})"
                                    )
                                    if count == 0:
                                        all_passed = False

                                elif key == "license_valid":
                                    license_status = report.get("license_status")
                                    if license_status == "valid":
                                        st.markdown("✅ **LICENSE is AGPLv3**")
                                    elif license_status == "gnu_other":
                                        st.markdown(
                                            "🟠 **LICENSE should be AGPLv3** — GNU license found (e.g., GPLv3/LGPLv3) but not AGPLv3"
                                        )
                                        all_passed = False
                                    else:
                                        st.markdown(
                                            "❌ **LICENSE should be AGPLv3** — License is non-GNU (e.g., MIT/Apache) or missing"
                                        )
                                        all_passed = False

                                elif key == "readme_status":
                                    rstatus = report.get("readme_status")
                                    if rstatus == "present":
                                        st.markdown("✅ **README present**")
                                    elif rstatus == "empty":
                                        st.markdown("❌ **README is empty**")
                                        all_passed = False
                                    else:
                                        st.markdown("❌ **README missing**")
                                        all_passed = False

                                else:
                                    emoji = "✅" if status else "❌"
                                    st.markdown(f"{emoji} **{display_name}**")
                                    if not status:
                                        all_passed = False

                    if all_passed:
                        st.success(
                            "🎉 **All Set!** Your project meets all compliance requirements."
                        )
                    else:
                        get_suggestions_for_missing_items(report)

                    # Conditional documentation
                    docs_map = {
                        "pyproject.toml": "- [`pyproject.toml`](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) – Configuration for Python project build system, dependencies, and packaging metadata.",
                        "vscode_settings": "- [`.vscode/settings.json`](https://code.visualstudio.com/docs/getstarted/settings) – Workspace-specific editor settings including linters and interpreter.",
                        "vscode_ruff_in_extensions": "- [Ruff in `.vscode/extensions.json`](https://docs.astral.sh/ruff/editors/setup/) – Recommend Ruff extension for linting.",
                        "vscode_extensions_exists": "- [`.vscode/extensions.json`](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#_workspace-recommended-extensions) – Recommend essential extensions.",
                        "vscode_launch_exists": "- [`.vscode/launch.json`](https://code.visualstudio.com/docs/debugtest/debugging) – Define debug profiles.",
                        "vscode_tasks_exists": "- [`.vscode/tasks.json`](https://code.visualstudio.com/docs/editor/tasks) – Automate common tasks.",
                        "uv_lock_exists": "- [`uv.lock`](https://docs.astral.sh/uv/concepts/projects/sync/) – Lock dependencies for reproducible environments.",
                    }

                    relevant_keys = [
                        "pyproject.toml",
                        "vscode_settings",
                        "vscode_ruff_in_extensions",
                        "vscode_extensions_exists",
                        "vscode_launch_exists",
                        "vscode_tasks_exists",
                        "uv_lock_exists",
                    ]
                    missing_keys = [k for k in relevant_keys if not report.get(k, False)]

                    if missing_keys:
                        st.markdown("---")
                        st.subheader("📖 Documentation for Missing Configuration Files")
                        with st.expander("Why these files matter", expanded=False):
                            for key in missing_keys:
                                doc_text = docs_map.get(key)
                                if doc_text:
                                    st.markdown(doc_text)

                    # --- Repository file categories & export for single project ---
                    st.markdown("---")
                    st.subheader("🧭 Repository File Categories & Export")

                    try:
                        files = list_all_files(project, branch=selected_branch)
                        classification = classify_repository_files(files)

                        st.markdown("**Language summary**")
                        st.write(f"Python files: {len(classification.get('python_files', []))}")
                        st.write(f"JS/TS files: {len(classification.get('js_files', []))}")

                        with st.expander("Common requirement files", expanded=False):
                            files = classification.get("common_requirements", [])
                            if files:
                                for f in files:
                                    st.markdown(f"- `{os.path.basename(f)}`")
                            else:
                                st.write("None")

                        with st.expander(
                            "Project files (README, docs, src, tests)", expanded=False
                        ):
                            files = classification.get("project_files", [])
                            if files:
                                for f in files:
                                    st.markdown(f"- `{os.path.basename(f)}`")
                            else:
                                st.write("None")

                        with st.expander("Tech / tooling files", expanded=False):
                            files = classification.get("tech_files", [])
                            if files:
                                for f in files:
                                    st.markdown(f"- `{os.path.basename(f)}`")
                            else:
                                st.write("None")
                        files = classification.get("tech_files", [])
                        if files:
                            for f in files:
                                st.markdown(f"- `{os.path.basename(f)}`")
                        else:
                            st.write("None")
                        # README quick summary
                        st.markdown("**README status**")
                        st.write(f"Status: {report.get('readme_status', 'missing')}")
                        readme_score = report.get("readme_quality_score")
                        if readme_score is not None:
                            render_readme_quality_progress_bar(readme_score)
                        if report.get("readme_sections"):
                            st.write(
                                f"Detected sections: {', '.join(report.get('readme_sections', []))}"
                            )

                        # Build a single-row summary for this project
                        single_row = {
                            "project_id": project.id,
                            "path": project.path_with_namespace,
                            "branch": selected_branch,
                            "python_count": len(classification.get("python_files", [])),
                            "js_count": len(classification.get("js_files", [])),
                            "java_count": len(classification.get("java_files", [])),
                            "go_count": len(classification.get("go_files", [])),
                            "rust_count": len(classification.get("rust_files", [])),
                            "csharp_count": len(classification.get("csharp_files", [])),
                            "detected_languages": ", ".join(
                                classification.get("detected_languages", [])
                            ),
                            "common_requirements": classification.get("common_requirements", []),
                            "project_files": classification.get("project_files", []),
                            "tech_files": classification.get("tech_files", []),
                            "license_status": report.get("license_status"),
                            "license_valid": report.get("license_valid"),
                            "readme_status": report.get("readme_status"),
                            "readme_quality_score": report.get("readme_quality_score", 0),
                            "readme_notes": ";".join(report.get("readme_sections", [])),
                        }

                        try:
                            excel_bytes = reports_to_excel([single_row])
                            st.download_button(
                                "Download Excel for this project",
                                data=excel_bytes,
                                file_name=f"{project.path_with_namespace.replace('/', '_')}_report.xlsx",
                                mime="application/octet-stream",
                            )
                        except Exception as e:
                            st.error(f"Could not create Excel for this project: {e}")
                            st.info(f"Tip: Install Excel writer support: {EXCEL_PIP_SUGGEST}")
                            csv_text = reports_to_csv([single_row])
                            st.warning("Falling back to CSV export.")
                            st.download_button(
                                "Download CSV for this project",
                                data=csv_text,
                                file_name=f"{project.path_with_namespace.replace('/', '_')}_report.csv",
                                mime="text/csv",
                            )
                    except Exception as e:
                        st.error(f"Error analyzing repository files: {e}")
                        st.exception(e)

        except Exception as e:
            st.error(f"Error accessing project: {str(e)}")

# ---------- MODE: User Profile Overview ----------
# ---------- MODE: User Profile Overview ----------
# ---------- MODE: User Profile Overview ----------
elif mode == "User Profile Overview":
    st.subheader("👤 User Profile Overview")

    username_input = st.text_input("Enter GitLab username")
    user_token = st.text_input("Enter GitLab Access Token (read_api)", type="password")

    fetch_clicked = st.button("Fetch User Groups")

    # Stop until button clicked
    if not fetch_clicked:
        st.stop()

    # Validate inputs
    if not username_input or not user_token:
        st.warning("Please enter BOTH username and access token.")
        st.stop()

    # Validate token → get authenticated user
    user_info = get_user_from_token(URL, user_token)

    if isinstance(user_info, str):
        st.error(user_info)
        st.stop()

    # Username must match token owner
    if user_info["username"] != username_input:
        st.error(
            f"❌ Token belongs to `{user_info['username']}`, but you entered `{username_input}`."
        )
        st.stop()
    # ---- Groups (logic stays SAME) ----
    groups = get_user_groups_by_token(URL, user_token)
    group_count = len(groups) if isinstance(groups, list) else "N/A"

    # ---- Account Statistics (UI same as old code) ----
    st.markdown("### 📊 Account Statistics")
    col1, col2 = st.columns(2)

    with col1:
        st.metric("Projects", "N/A")
        st.metric("Groups", group_count)

    with col2:
        st.metric("Open Issues", "N/A")
        st.metric("Open MRs", "N/A")

    # ---- User Info UI ----
    st.markdown(
        f"""
### 👤 {user_info["name"]}
**Username:** @{user_info["username"]}
**User ID:** {user_info["id"]}
"""
    )

    if user_info.get("avatar_url"):
        st.image(user_info["avatar_url"], width=80)

    st.markdown(f"[View GitLab Profile]({user_info['web_url']})")

    # ---- Groups ----
    groups = get_user_groups_by_token(URL, user_token)

    st.markdown("### 👥 Groups")

    if isinstance(groups, str):
        st.error(groups)
    elif not groups:
        st.info("User is not part of any groups.")
    else:
        st.metric("Number of Groups", len(groups))

        for i, g in enumerate(groups, 1):
            with st.expander(f"{i}. {g['name']}"):
                st.write(f"Full Path: {g['full_path']}")
                st.write(f"Visibility: {g['visibility']}")
                st.markdown(f"[Open Group]({g['web_url']})")
