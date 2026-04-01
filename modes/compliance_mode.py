import concurrent.futures
import http.client
import time
from urllib.parse import urlparse

import streamlit as st
from gitlab import GitlabGetError

from Projects.tools_checker import check_tools

# --- Helper Functions (copied/adapted from app.py) ---


@st.cache_data(ttl=60)
def read_file_content(_project, file_path, ref):
    try:
        file = _project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None


def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return gl_client.projects.get(int(path_or_id) if str(path_or_id).isdigit() else path_or_id)
        except GitlabGetError as e:
            last_exc = e
            if getattr(e, "response", None) is not None and e.response.status_code == 404:
                raise
            if attempt == retries:
                raise
        except (
            ConnectionResetError,
            ConnectionAbortedError,
            OSError,
            http.client.RemoteDisconnected,
            Exception,
        ) as e:
            last_exc = e
            if type(e).__name__ not in ("RequestException", "ConnectionError", "Timeout"):
                if not isinstance(e, (OSError, http.client.RemoteDisconnected)):
                    raise
            if attempt == retries:
                raise
            sleep_for = backoff * (2 ** (attempt - 1))
            time.sleep(sleep_for)
    if last_exc:
        raise last_exc


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
    content = read_file_content(project, "LICENSE", branch) or read_file_content(project, "LICENSE.md", branch)
    if not content:
        return "not_found"

    cleaned = " ".join(content.strip().split()).lower()
    has_affero = "affero" in cleaned
    has_gpl = "general public license" in cleaned
    has_version_3 = "version 3" in cleaned or "v3" in cleaned or "3.0" in cleaned
    has_correct_agpl_date = "19 november 2007" in cleaned

    if has_affero and has_gpl and has_version_3 and has_correct_agpl_date:
        return "valid"

    has_correct_gplv3_date = "29 june 2007" in cleaned
    is_gplv3 = has_gpl and has_version_3 and has_correct_gplv3_date and not has_affero
    has_lgpl = "lgpl" in cleaned or "lesser general public license" in cleaned
    has_correct_lgpl_date = "29 june 2007" in cleaned
    is_lgplv3 = has_lgpl and has_version_3 and has_correct_lgpl_date

    if is_gplv3 or is_lgplv3:
        return "gnu_other"

    has_gnu = "gnu" in cleaned
    has_gpl_v2 = "version 2" in cleaned or "v2" in cleaned or "2.0" in cleaned
    has_gpl_general = has_gpl and not has_affero

    if (
        (has_gnu and has_gpl_general and (has_version_3 or has_gpl_v2))
        or (has_lgpl and (has_version_3 or has_gpl_v2))
        or (has_gpl_general and (has_version_3 or has_gpl_v2))
    ):
        return "gnu_other"

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

    if "license" in cleaned and "copyright" in cleaned:
        if has_gnu or has_gpl or has_lgpl:
            return "gnu_other"
        return "invalid"

    return "invalid"


def check_vscode_settings_content(project, branch="main"):
    content = read_file_content(project, ".vscode/settings.json", branch)
    return {"exists": content is not None}


def check_extensions_json_for_ruff(project, branch="main"):
    content = read_file_content(project, ".vscode/extensions.json", branch)
    if not content:
        return False
    try:
        import json

        config = json.loads(content)
        recommendations = config.get("recommendations", [])
        return "charliermarsh.ruff" in recommendations or any("ruff" in ext.lower() for ext in recommendations)
    except Exception:
        return False


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
    }
    report = {}
    try:
        branch = branch or getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        for label, variants in required_files.items():
            report[label] = any(variant.lower() in filenames for variant in variants)

        readme_present = any(n for n in filenames if n.startswith("readme"))
        report["README.md"] = readme_present
        if readme_present:
            content = read_file_content(project, "README.md", branch) or read_file_content(project, "README", branch)
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

        license_variants = ["LICENSE", "LICENSE.md"]
        report["LICENSE"] = any(variant.lower() in filenames for variant in license_variants)
        if report["LICENSE"]:
            license_status = check_license_content(project, branch)
        else:
            license_status = "not_found"
        report["license_valid"] = license_status == "valid"
        report["license_status"] = license_status

        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames
        report["uv_lock_exists"] = "uv.lock" in filenames
        report["package_json"] = "package.json" in filenames
        report["package_lock_exists"] = "package-lock.json" in filenames
        report["yarn_lock_exists"] = "yarn.lock" in filenames
        report["bun_lock_exists"] = "bun.lock" in filenames or "bun.lockb" in filenames
        report["husky_exists"] = ".husky" in filenames
        report[".gitlab-ci.yml"] = ".gitlab-ci.yml" in filenames
        report[".pre-commit-config.yaml"] = ".pre-commit-config.yaml" in filenames

        template_details = check_templates_presence(project, branch)
        report.update(template_details)

        report["description_present"] = bool(project.description and project.description.strip())
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0
        
        # Tools & Language Classification
        report["language"] = classify_project_language(filenames)
        report["tools"] = check_tools(project.manager.gitlab, project.id)

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report


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


def classify_project_language(filenames):
    """Simple classification based on presence of key files."""
    is_python = any(
        f in filenames
        for f in ["pyproject.toml", "requirements.txt", "setup.py", "tox.ini", "pipfile", "uv.lock"]
    ) or any(f.endswith(".py") for f in filenames)
    
    is_js = any(
        f in filenames
        for f in [
            "package.json", 
            "package-lock.json", 
            "yarn.lock", 
            "bun.lock", 
            "bun.lockb",
            "tsconfig.json", 
            "next.config.js"
        ]
    ) or any(f.endswith((".js", ".ts", ".tsx", ".jsx")) for f in filenames) or ".husky" in filenames
    
    if is_python and is_js:
        return "Python & JS"
    if is_python:
        return "Python"
    if is_js:
        return "JS/TS"
    return "Unknown"


def get_suggestions_for_missing_items(report):
    st.subheader("📌 Suggestions for Missing Items")
    
    # Core suggestions (Language Independent)
    core_suggestions = [
        ("README.md", "README.md missing", "Add a `README.md` file."),
        ("CONTRIBUTING.md", "CONTRIBUTING.md missing", "Add a `CONTRIBUTING.md` file."),
        ("CHANGELOG", "CHANGELOG missing", "Maintain a `CHANGELOG.md` file."),
        ("LICENSE", "LICENSE missing", "Include an `AGPLv3 LICENSE` file."),
        ("license_valid", "LICENSE is not AGPLv3", "Ensure the license is AGPLv3."),
        (".gitignore", ".gitignore missing", "Add a `.gitignore` file."),
        (".gitlab-ci.yml", ".gitlab-ci.yml missing", "Add a `.gitlab-ci.yml` to enable CI/CD."),
        (".pre-commit-config.yaml", ".pre-commit-config.yaml missing", "Add `.pre-commit-config.yaml` for automated hooks."),
        ("description_present", "Project description missing", "Provide a project description in GitLab settings."),
        ("tags_present", "Project tags missing", "Tag your project releases/milestones."),
    ]

    for key, display_name, suggestion_text in core_suggestions:
        if not report.get(key, True):
            st.markdown(f"❌ **{display_name}** — {suggestion_text}")

    # Language-specific suggestions
    lang = report.get("language", "Unknown")
    if "Python" in lang:
        if not report.get("pyproject.toml"):
            st.markdown("❌ **pyproject.toml missing** — Recommended for Python projects.")
        if not report.get("uv_lock_exists"):
            st.markdown("🟡 **uv.lock missing** — Consider using `uv` for reproducible builds.")
    
    if "JS" in lang:
        if not report.get("package_json"):
            st.markdown("❌ **package.json missing** — Essential for JS projects.")
        
        has_js_lock = report.get("package_lock_exists") or report.get("yarn_lock_exists") or report.get("bun_lock_exists")
        if not has_js_lock:
            st.markdown("❌ **JS Lock file missing** — Add `package-lock.json`, `yarn.lock`, or `bun.lock`.")

    readme_status = report.get("readme_status")
    if readme_status == "missing":
        st.markdown("❌ **README missing** — Add a `README.md`.")
    elif readme_status == "empty":
        st.markdown("❌ **README is empty** — Add meaningful content.")
    elif report.get("readme_needs_improvement"):
        st.markdown("🟡 **README needs improvement** — Consider adding Installation/Usage/License/Contributing.")


def render_project_compliance_ui(report, project=None, branch=None, _classification=None):
    if report.get("error"):
        st.error(report["error"])
        return

    st.markdown("### 📋 Compliance Summary by Category")
    
    # Classification badge
    lang = report.get("language", "Unknown")
    st.info(f"Detected Project Language: **{lang}**")

    # Metadata & Documentation
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**1. 📄 Metadata & Repo Setup**")
        metadata_items = {
            "description_present": "Project Description",
            "tags_present": "Tags",
            ".gitignore": ".gitignore",
            ".gitlab-ci.yml": "GitLab CI config",
            ".pre-commit-config.yaml": "Pre-commit config",
        }
        for key, label in metadata_items.items():
            icon = "✅" if report.get(key) else "❌"
            st.write(f"{icon} {label}")

    with col2:
        st.markdown("**2. 📚 Documentation**")
        docs_items = {
            "README.md": "README.md",
            "CONTRIBUTING.md": "CONTRIBUTING.md",
            "CHANGELOG": "CHANGELOG",
            "LICENSE": "LICENSE",
            "license_valid": "LICENSE is AGPLv3",
            "issue_templates_folder": "Issue Templates Folder",
            "merge_request_templates_folder": "Merge Request Templates Folder",
        }
        for key, label in docs_items.items():
            icon = "✅" if report.get(key) else "❌"
            st.write(f"{icon} {label}")

    # Configuration (Language Specific)
    st.markdown("**3. ⚙️ Configuration**")
    config_col1, config_col2 = st.columns(2)
    with config_col1:
        if "Python" in lang:
            st.write("✅" if report.get("pyproject.toml") else "❌", "pyproject.toml")
            st.write("✅" if report.get("uv_lock_exists") else "❌", "uv.lock")
        
        if "JS" in lang:
            st.write("✅" if report.get("package_json") else "❌", "package.json")
            has_js_lock = report.get("package_lock_exists") or report.get("yarn_lock_exists") or report.get("bun_lock_exists")
            lock_label = "JS Lock File (package-lock/yarn/bun)"
            st.write("✅" if has_js_lock else "❌", lock_label)
            st.write("✅" if report.get("husky_exists") else "🔍", ".husky (directory)")
        
        if "Python" not in lang and "JS" not in lang:
            st.write("No specific configuration checks for this language.")

    # 🛠 Tools Analysis
    st.markdown("**4. 🛠 Tools Detected (CI/Pre-commit)**")
    tools = report.get("tools", {})
    if "error" in tools:
        st.error(f"Error checking tools: {tools['error']}")
    else:
        for category, tool_dict in tools.items():
            active_tools = [tool for tool, present in tool_dict.items() if present]
            if active_tools:
                st.markdown(f"**{category.replace('_', ' ').title()}**: {', '.join(active_tools)}")

def render_compliance_mode(gl_client):
    st.subheader("🔍 Project Compliance Checker")

    tabs = st.tabs(["Single Project", "Batch Projects"])

    with tabs[0]:
        st.markdown("#### Check a Single Project")

        # State management for Single Project
        if "compliance_project_id" not in st.session_state:
            st.session_state["compliance_project_id"] = ""

        project_input = st.text_input(
            "Enter Project ID or URL",
            value=st.session_state["compliance_project_id"],
            key="single_project_input",
            placeholder="https://gitlab.com/group/project",
        )

        col1, col2 = st.columns([1, 4])
        with col1:
            fetch_clicked = st.button("Fetch Project")

        if fetch_clicked and project_input:
            st.session_state["compliance_project_id"] = project_input
            try:
                with st.spinner("Fetching project..."):
                    pid = extract_path_from_url(project_input)
                    project = get_project_with_retries(gl_client, pid)
                    st.session_state["current_project"] = project
                    st.session_state["current_project_branches"] = get_project_branches(project)
                    st.success(f"Loaded: **{project.name_with_namespace}**")
                    st.rerun()
            except Exception as e:
                st.error(f"Error fetching project: {e}")

        # Display Project Info & Run Analysis if loaded
        if "current_project" in st.session_state and st.session_state.get("compliance_project_id") == project_input:
            project = st.session_state["current_project"]
            st.info(f"Active Project: **{project.name_with_namespace}** ({project.web_url})")

            branches = st.session_state.get("current_project_branches", [])
            default_branch_idx = 0
            if hasattr(project, "default_branch") and project.default_branch in branches:
                default_branch_idx = branches.index(project.default_branch)

            branch = st.selectbox("Select Branch", branches, index=default_branch_idx)

            if st.button("Run Analysis", key="run_analysis_single"):
                with st.spinner("Analyzing..."):
                    report = check_project_compliance(project, branch)
                    render_project_compliance_ui(report, project, branch)
                    get_suggestions_for_missing_items(report)

    with tabs[1]:
        st.markdown("#### Batch Check Multiple Projects")
        render_batch_project_compliance_internal(gl_client)


def render_batch_project_compliance_internal(gl_client):
    project_input = st.text_area(
        "Enter Project IDs or URLs (one per line)",
        height=150,
        placeholder="https://gitlab.com/group/project1\n12345\n...",
    )

    if st.button("Run Batch Analysis", key="run_batch_btn"):
        lines = [line.strip() for line in project_input.splitlines() if line.strip()]
        if not lines:
            st.warning("Please enter at least one project.")
            return

        results = []
        progress_bar = st.progress(0)

        def _process_line(line):
            """Worker to process a single project line."""
            try:
                pid = extract_path_from_url(line)
                project = get_project_with_retries(gl_client, pid)
                report = check_project_compliance(project)

                # Summarize for table
                row = {
                    "Project": project.name_with_namespace,
                    "URL": project.web_url,
                    "README": "✅" if report.get("readme_status") == "present" else "❌",
                    "LICENSE": "✅" if report.get("license_valid") else "❌",
                    "VSCode": "✅" if report.get("vscode_config_exists") else "❌",
                    "Metdata": "✅" if report.get("description_present") else "❌",
                    "CI/CD": "✅" if report.get(".gitlab-ci.yml") else "❌",
                    "GitProcess": "✅"
                    if report.get("issue_templates_folder") or report.get("merge_request_templates_folder")
                    else "❌",
                }
                if report.get("error"):
                    row["Error"] = report["error"]
                return row
            except Exception as e:
                return {"Project": line, "Error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_line = {executor.submit(_process_line, line): line for line in lines}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_line)):
                results.append(future.result())
                progress_bar.progress((i + 1) / len(lines))

        if results:
            st.write("### 📊 Batch Summary")
            st.dataframe(results)

            # Excel Export
            try:
                from io import BytesIO

                import pandas as pd

                df = pd.DataFrame(results)
                output = BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Batch Compliance")
                st.download_button(
                    label="Download Batch Report",
                    data=output.getvalue(),
                    file_name="batch_compliance_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception:
                pass
