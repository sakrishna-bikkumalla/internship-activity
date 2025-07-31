import os
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv
from gitlab import Gitlab, GitlabGetError
from gitlab.v4.objects import Project
from gitlab_utils.client import GitLabClient  # For user APIs only


# --- Optimize: Cache file reads ---
@st.cache_data(ttl=60)
def read_file_content(_project, file_path, ref):
    try:
        file = _project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None


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
        md_files = [
            item["name"] for item in items if item["name"].lower().endswith(".md")
        ]
        if md_files:
            result["issue_templates_folder"] = True
            result["issue_template_files"] = md_files
    except Exception:
        pass
    try:
        items = project.repository_tree(
            path=".gitlab/merge_request_templates", ref=branch
        )
        md_files = [
            item["name"] for item in items if item["name"].lower().endswith(".md")
        ]
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

        # Check LICENSE existence and validity
        license_variants = ["LICENSE", "LICENSE.md"]
        report["LICENSE"] = any(
            variant.lower() in filenames for variant in license_variants
        )

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
        report["vscode_ruff_in_extensions"] = check_extensions_json_for_ruff(
            project, branch
        )

        # Other VSCode files
        report["vscode_extensions_exists"] = check_vscode_file_exists(
            project, "extensions.json", branch
        )
        report["vscode_launch_exists"] = check_vscode_file_exists(
            project, "launch.json", branch
        )
        report["vscode_tasks_exists"] = check_vscode_file_exists(
            project, "tasks.json", branch
        )

        # Templates
        template_details = check_templates_presence(project, branch)
        report.update(template_details)

        # Metadata
        report["description_present"] = bool(
            project.description and project.description.strip()
        )
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report


# Patch Project class
def patch_gitlab_project():
    Project.check_compliance = lambda self, branch=None: check_project_compliance(
        self, branch
    )


patch_gitlab_project()


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
    show_files_image = not report.get(
        "issue_templates_folder", False
    ) or not report.get("merge_request_templates_folder", False)
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
    st.error(
        "❌ GITLAB_TOKEN or GITLAB_URL not found. Please set them in secrets or .env."
    )
    st.stop()

client = GitLabClient(base_url=URL, private_token=TOKEN)  # For user APIs
gl = Gitlab(URL, private_token=TOKEN)  # For project APIs

st.title("GitLab Tools")
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
                project = gl.projects.get(int(path_or_id) if is_id else path_or_id)
                st.session_state["selected_project_id"] = project.id
                branches = get_project_branches(project)
                st.session_state["branches"] = branches
            except GitlabGetError:
                st.error(f"Project '{path_or_id}' not found.")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []
            except Exception as e:
                st.error(f"Unexpected error: {str(e)}")
                st.session_state["selected_project_id"] = None
                st.session_state["branches"] = []

    selected_project_id = st.session_state.get("selected_project_id")
    branches = st.session_state.get("branches") or []

    if selected_project_id:
        try:
            project = gl.projects.get(selected_project_id)
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
                st.warning(
                    "No branches found, will check default/main branch if possible."
                )

            run_check = st.button(
                "Run Compliance Check on Selected Branch", key="run_compliance_check"
            )
            run_automatic = len(branches) == 1 and (branches[0] == default_branch)

            if run_check or run_automatic:
                report = check_project_compliance(
                    project=project, branch=selected_branch
                )
                st.write(
                    f"### Project: {project.path_with_namespace} (ID: {project.id}) | Branch: `{selected_branch}`"
                )

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
                            "license_valid": "LICENSE is AGPLv3",
                            "issue_templates_folder": "Issue Templates Folder (.gitlab/issue_templates)",
                            "issue_template_files": "Issue Template Files",
                            "merge_request_templates_folder": "Merge Request Templates Folder (.gitlab/merge_request_templates)",
                            "merge_request_template_files": "Merge Request Template Files",
                        },
                        "3. ⚙️ Project Configuration": {
                            ".gitignore": ".gitignore",
                            "pyproject.toml": "pyproject.toml",
                            "uv_lock_exists": "uv.lock",
                            "vscode_settings": ".vscode/settings.json",
                            "vscode_ruff_in_extensions": "Ruff in .vscode/extensions.json",
                            "vscode_extensions_exists": ".vscode/extensions.json",
                            "vscode_launch_exists": ".vscode/launch.json",
                            "vscode_tasks_exists": ".vscode/tasks.json",
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
                                    listed = (
                                        ", ".join(sorted(status)) if status else "None"
                                    )
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
                                            "🟠 **LICENSE is AGPLv3** — GNU license found (e.g., GPLv3/LGPLv3) but not AGPLv3"
                                        )
                                        all_passed = False
                                    else:
                                        st.markdown(
                                            "❌ **LICENSE is AGPLv3** — License is non-GNU (e.g., MIT/Apache) or missing"
                                        )
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
                    missing_keys = [
                        k for k in relevant_keys if not report.get(k, False)
                    ]

                    if missing_keys:
                        st.markdown("---")
                        st.subheader("📖 Documentation for Missing Configuration Files")
                        with st.expander("Why these files matter", expanded=False):
                            for key in missing_keys:
                                doc_text = docs_map.get(key)
                                if doc_text:
                                    st.markdown(doc_text)

        except Exception as e:
            st.error(f"Error accessing project: {str(e)}")

# ---------- MODE: User Profile Overview ----------
elif mode == "User Profile Overview":
    st.subheader("👤 User Profile Overview")
    user_input = st.text_input(
        "Enter GitLab username, user ID, or profile URL",
        key="user_overview_input",
        on_change=lambda: setattr(st.session_state, "user_overview_triggered", True),
    )
    check_triggered = st.session_state.get("user_overview_triggered", False)
    button_clicked = st.button(
        "Fetch User Info & Check README", key="user_overview_button"
    )

    if check_triggered or button_clicked:
        st.session_state["user_overview_triggered"] = False
        input_val = user_input.strip()
        if not input_val:
            st.warning("Please enter a username, user ID, or profile URL.")
        else:
            # --- Step 1: Get User Info using `client` ---
            try:
                if input_val.isdigit():
                    user_info = client.users.get_by_userid(int(input_val))
                else:
                    username = extract_path_from_url(input_val)
                    user_info = client.users.get_by_username(username)
            except Exception as e:
                st.error(f"❌ User not found or error (via client): {e}")
                user_info = None

            if not user_info:
                st.stop()

            # Display user info from `client`
            st.write(
                f"### User: **{user_info['name']}** (@{user_info['username']}, ID: {user_info['id']})"
            )
            if user_info.get("avatar_url"):
                st.image(user_info["avatar_url"], width=80)
            st.write(f"[View GitLab Profile]({user_info.get('web_url', '')})")

            # Show stats using `client` APIs
            st.markdown("#### 📊 Account Statistics")
            col1, col2 = st.columns(2)

            proj_count = client.users.get_user_project_count(user_info["id"])
            group_count = client.users.get_user_group_count(user_info["id"])
            issue_count = client.users.get_user_issue_count(user_info["id"])
            mr_count = client.users.get_user_mr_count(user_info["id"])

            with col1:
                st.metric(
                    "Projects", proj_count if isinstance(proj_count, int) else "N/A"
                )
                st.metric(
                    "Groups", group_count if isinstance(group_count, int) else "N/A"
                )
            with col2:
                st.metric(
                    "Open Issues",
                    issue_count if isinstance(issue_count, int) else "N/A",
                )
                st.metric("Open MRs", mr_count if isinstance(mr_count, int) else "N/A")

            # Warn if any metric failed
            for label, count in [
                ("projects", proj_count),
                ("groups", group_count),
                ("issues", issue_count),
                ("merge requests", mr_count),
            ]:
                if isinstance(count, str) and count.startswith("Error:"):
                    st.warning(f"Could not get {label} count: {count[6:].strip()}")

            # --- Step 2: Check Profile README using `gl` ---
            st.markdown("#### 📄 Profile README Status")

            def check_readme_in_project(project):
                try:
                    branch = getattr(project, "default_branch", "main")
                    tree = project.repository_tree(ref=branch)
                    filenames = [item["name"].lower() for item in tree]
                    return "readme.md" in filenames
                except Exception as e:
                    st.warning(f"Error checking README: {str(e)}")
                    return False

            def check_user_profile_readme(gl_client, username):
                try:
                    # Try to get project: <username>/<username>
                    project_path = f"{username}/{username}"
                    profile_project = gl_client.projects.get(project_path)
                    # Confirm it's in user namespace
                    if (
                        profile_project.namespace["full_path"].lower()
                        == username.lower()
                    ):
                        has_readme = check_readme_in_project(profile_project)
                        return has_readme, profile_project
                except GitlabGetError:
                    pass  # Project not found
                except Exception as e:
                    st.warning(f"Error accessing profile project: {e}")
                return False, None

            # Use `gl` to check README (not `client`)
            has_readme, profile_project = check_user_profile_readme(
                gl, user_info["username"]
            )

            if profile_project is None:
                st.info("❌ No profile project found (i.e., `<username>/<username>`).")
                st.markdown(
                    "💡 **Suggestion**: Create a README for your profile by following these steps:"
                )
                st.markdown(
                    "1. Create a new project with the exact same name as your username"
                )
                st.markdown("2. Add a `README.md` file in that project")
                st.markdown("3. This README will appear on your GitLab profile page")
                try:
                    st.image(
                        "assets/Readme.png",
                        caption="Example of a profile README setup",
                        width=500,
                    )
                except Exception:
                    pass
            elif has_readme:
                branch = getattr(profile_project, "default_branch", "main")
                st.success("✅ Profile README is set up correctly!")
                domain = urlparse(URL).netloc
                url = f"https://{domain}/{profile_project.path_with_namespace}/-/blob/{branch}/README.md"
                st.markdown(f"[View README]({url})")
            else:
                st.error("❌ Profile project exists but is missing `README.md`.")
                try:
                    st.image("assets/Readme.png", width=400)
                except Exception:
                    pass
