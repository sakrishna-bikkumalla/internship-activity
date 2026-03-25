"""
GitLab API helpers for compliance checking and project analysis.
No Streamlit dependencies.
"""

import os


def extract_path_from_url(input_str):
    """Extract raw project path from GitLab URL or return path as-is.

    Args:
        input_str: Raw project path, URL, or project ID

    Returns:
        GitLab-compatible project identifier
    """
    from urllib.parse import urlparse

    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return input_str.strip()


def get_project_branches(project):
    """Fetch all branches from a project.

    Args:
        project: GitLab project object

    Returns:
        Sorted list of branch names
    """
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


def list_all_files(project, branch="main"):
    """Return list of file paths (blobs) in the repository (recursive).

    Args:
        project: GitLab project object
        branch: Branch name to query

    Returns:
        List of file paths
    """
    try:
        # Try with common params
        items = project.repository_tree(ref=branch, recursive=True, all=True)
    except TypeError:
        # Fallback if 'all' not supported by the API client
        items = project.repository_tree(ref=branch, recursive=True)
    files = [item.get("path") for item in items if item.get("type") == "blob"]
    return files


def classify_repository_files(file_paths):
    """Classify files into categories and detect language files.

    Args:
        file_paths: List of file paths

    Returns:
        Dict with classification results
    """
    res = {
        "common_requirements": [],
        "project_files": [],
        "tech_files": [],
        "python_files": [],
        "js_files": [],
        "java_files": [],
        "c#_files": [],
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

        # Language-specific
        if lp.endswith(".py"):
            res["python_files"].append(p)
        if lp.endswith((".js", ".jsx", ".ts", ".tsx")):
            res["js_files"].append(p)

    # Deduplicate lists
    for k in res:
        res[k] = sorted(dict.fromkeys(res[k]))
    return res


def check_vscode_settings(project, branch="main"):
    """Check if .vscode/settings.json exists in project.

    Args:
        project: GitLab project object
        branch: Branch name to check

    Returns:
        Boolean indicating if settings.json exists
    """
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return "settings.json" in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_vscode_file_exists(project, filename, branch="main"):
    """Check if a specific file exists in .vscode directory.

    Args:
        project: GitLab project object
        filename: File to check for
        branch: Branch name to check

    Returns:
        Boolean indicating if file exists
    """
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return filename.lower() in [item["name"].lower() for item in items]
    except Exception:
        return False


def check_extensions_json_for_ruff(project, branch="main", read_file_fn=None):
    """Check if Ruff is recommended in .vscode/extensions.json.

    Args:
        project: GitLab project object
        branch: Branch name to check
        read_file_fn: Optional file reading function (defaults to reading from project API)

    Returns:
        Boolean indicating if Ruff is in recommendations
    """
    if read_file_fn is None:
        # Import here to avoid circular dependencies
        from gitlab_utils.file_reader import read_file_content_no_cache

        read_file_fn = read_file_content_no_cache

    content = read_file_fn(project, ".vscode/extensions.json", branch)
    if not content:
        return False
    try:
        import json

        config = json.loads(content)
        recommendations = config.get("recommendations", [])
        return "charliermarsh.ruff" in recommendations or any("ruff" in ext.lower() for ext in recommendations)
    except Exception:
        return False


def list_markdown_files_in_folder(project, folder_path, branch="main"):
    """List all markdown files in a folder.

    Args:
        project: GitLab project object
        folder_path: Path to folder
        branch: Branch name to check

    Returns:
        List of markdown file names
    """
    try:
        items = project.repository_tree(path=folder_path, ref=branch)
        return [item["name"] for item in items if item["name"].lower().endswith(".md")]
    except Exception:
        return []


def check_templates_presence(project, branch="main"):
    """Check for GitLab issue and merge request templates.

    Args:
        project: GitLab project object
        branch: Branch name to check

    Returns:
        Dict with template presence information
    """
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


def check_license_content(project, branch="main", read_file_fn=None):
    """Check if license is AGPLv3, other GNU, or invalid.

    Args:
        project: GitLab project object
        branch: Branch name to check
        read_file_fn: Optional file reading function

    Returns:
        String indicating license status: 'valid', 'gnu_other', or 'invalid'
    """
    if read_file_fn is None:
        from gitlab_utils.file_reader import read_file_content_no_cache

        read_file_fn = read_file_content_no_cache

    content = read_file_fn(project, "LICENSE", branch) or read_file_fn(project, "LICENSE.md", branch)
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


def check_project_compliance(project, branch=None, read_file_fn=None):
    """Check project compliance with various standards.

    Args:
        project: GitLab project object
        branch: Branch name to check (defaults to default branch)
        read_file_fn: Optional file reading function

    Returns:
        Dict with compliance report
    """
    if read_file_fn is None:
        from gitlab_utils.file_reader import read_file_content_cached

        read_file_fn = read_file_content_cached

    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md"],
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
            content = read_file_fn(project, "README.md", branch) or read_file_fn(project, "README", branch)
            if not content or not content.strip():
                report["readme_status"] = "empty"
                report["readme_sections"] = []
                report["readme_needs_improvement"] = True
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
                report["readme_needs_improvement"] = len(found_sections) < 3 or len(content.strip()) < 150
        else:
            report["readme_status"] = "missing"
            report["readme_sections"] = []
            report["readme_needs_improvement"] = True

        # Check LICENSE existence and validity
        license_variants = ["LICENSE", "LICENSE.md"]
        report["LICENSE"] = any(variant.lower() in filenames for variant in license_variants)

        if report["LICENSE"]:
            license_status = check_license_content(project, branch, read_file_fn)
        else:
            license_status = "not_found"

        report["license_valid"] = license_status == "valid"
        report["license_status"] = license_status

        # Other files
        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames
        report["uv_lock_exists"] = "uv.lock" in filenames

        # VSCode config
        report["vscode_settings"] = check_vscode_settings(project, branch)
        vscode_content_exists = check_vscode_file_exists(project, "settings.json", branch)
        report["vscode_config_exists"] = vscode_content_exists

        # Ruff check in extensions.json
        report["vscode_ruff_in_extensions"] = check_extensions_json_for_ruff(project, branch, read_file_fn)

        # Other VSCode files
        report["vscode_extensions_exists"] = check_vscode_file_exists(project, "extensions.json", branch)
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
