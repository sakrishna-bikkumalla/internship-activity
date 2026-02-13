import streamlit as st
import os
from dotenv import load_dotenv
<<<<<<< HEAD
import os
from pathlib import Path
import importlib.util

# UI modules
from projects.project_ui import render_project_section

def _load_issue_ui_module():
    """Load issues/issue.ui.py safely (filename contains a dot)."""
    issue_ui_path = Path(__file__).resolve().parent / "issues" / "issue.ui.py"
    if not issue_ui_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("issues_issue_ui", issue_ui_path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_issue_section(gitlab_url, gitlab_token):
    """Issue dashboard section using available service/ui modules."""
    st.subheader("🧾 Issues Dashboard")

    project_ref = st.text_input(
        "Enter Project ID or Full Path",
        placeholder="e.g. 12345 or group/subgroup/project",
        key="issues_project_ref",
    )
    branch = st.text_input("Branch", value="main", key="issues_branch")

    if not st.button("Run Issue Checks", key="run_issue_checks"):
        return

    if not project_ref.strip():
        st.warning("Please enter a valid project ID or path.")
        return

    try:
        import gitlab
        from issues.issue_service import get_issue_summary

        gl = gitlab.Gitlab(gitlab_url, private_token=gitlab_token)
        project = gl.projects.get(project_ref.strip())
        summary = get_issue_summary(project, branch=branch.strip() or "main")

        issue_ui = _load_issue_ui_module()
        templates = summary.get("templates", {})

        if issue_ui and hasattr(issue_ui, "render_issue_compliance_ui"):
            issue_ui.render_issue_compliance_ui(templates)
            if hasattr(issue_ui, "render_issue_suggestions"):
                issue_ui.render_issue_suggestions(templates)
        else:
            st.markdown("### Issue Template Status")
            st.json(templates)

        st.markdown("### Issue Summary")
        st.json(summary)
    except Exception as e:
        st.error(f"Failed to run issue checks: {e}")


from user_profile.render_user_profile import render_user_profile


def render_user_profile_section(gitlab_url, gitlab_token):
    import gitlab

    gl = gitlab.Gitlab(gitlab_url, private_token=gitlab_token)
    render_user_profile(gl)


def render_batch_section(gitlab_url, gitlab_token):
    """Batch mode placeholder UI (kept stable even if backend modules vary)."""
    st.subheader("📚 Batch Compliance")
    st.info(
        "Batch processing UI is currently not wired in app.py. "
        "Backend modules exist, but no stable render_batch_section() is exposed yet."
    )

    projects_text = st.text_area(
        "Project IDs/Paths (one per line)",
        placeholder="group/project-one\n12345\norg/team/project-two",
        key="batch_project_refs",
    )
    refs = [line.strip() for line in projects_text.splitlines() if line.strip()]
    st.caption(f"Detected {len(refs)} project reference(s).")


# ----------------------------
# Environment Setup
# ----------------------------
load_dotenv()

def _get_secret(key: str):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


GITLAB_TOKEN = _get_secret("GITLAB_TOKEN") or os.getenv("GITLAB_TOKEN")
GITLAB_URL = _get_secret("GITLAB_URL") or os.getenv("GITLAB_URL")

if not GITLAB_TOKEN or not GITLAB_URL:
    st.error("❌ GITLAB_TOKEN or GITLAB_URL not found.")
    st.stop()


# ----------------------------
# Main App
# ----------------------------
def main():
    st.set_page_config(page_title="GitLab Compliance Checker", layout="wide")

    st.title("🚀 GitLab Compliance & Analytics Tool")
=======

# --- Page Config ---
st.set_page_config(
    page_title="GitLab Compliance Checker",
    page_icon="🔍",
    layout="wide",
)

# Load environment variables
load_dotenv()

# Import local modules
try:
    from gitlab_utils.client import GitLabClient
    from gitlab_utils import users

    # New UI Modules
    from modes.compliance_mode import render_compliance_mode
    from modes.user_profile import render_user_profile
    from modes.batch_mode import render_batch_mode_ui

except ImportError as e:
    st.error(f"Import Error: {e}")
    st.stop()

def main():
    st.title("GitLab Compliance & Analytics Tool")

    # Sidebar: Config & Mode
    st.sidebar.header("Configuration")

    # Credentials (allow override or from env)
    default_url = os.getenv("GITLAB_URL", "https://gitlab.com")
    default_token = os.getenv("GITLAB_TOKEN", "")

    gitlab_url = st.sidebar.text_input("GitLab URL", value=default_url)
    gitlab_token = st.sidebar.text_input("GitLab Token", value=default_token, type="password")
>>>>>>> origin/feature-final

    mode = st.sidebar.radio(
        "Select Mode",
        [
<<<<<<< HEAD
            "Project Compliance",
            "Issues Dashboard",
            "User Profile Overview",
            "Batch Compliance",
        ],
    )

    if mode == "Project Compliance":
        render_project_section(GITLAB_URL, GITLAB_TOKEN)

    elif mode == "Issues Dashboard":
        render_issue_section(GITLAB_URL, GITLAB_TOKEN)

    elif mode == "User Profile Overview":
        render_user_profile_section(GITLAB_URL, GITLAB_TOKEN)

    elif mode == "Batch Compliance":
        render_batch_section(GITLAB_URL, GITLAB_TOKEN)

=======
            "Check Project Compliance",
            "User Profile Overview",
            "Batch 2026 ICFAI",
            "Batch 2026 RCTS",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### About")
    st.sidebar.info(
        "Refactored Tool:\n"
        "- Project Compliance\n"
        "- User Analytics (Single & Batch)\n"
        "- Groups, MRs, Issues, Commits"
    )

    if not gitlab_token:
        st.warning("Please enter a GitLab Token in the sidebar or .env file.")
        st.stop()

    # Initialize Client
    client = GitLabClient(gitlab_url, gitlab_token)
    if not client.client:
        st.error("Failed to initialize GitLab client. Check URL and Token.")
        st.stop()

    # Routing
    if mode == "Check Project Compliance":
        # Compliance mode expects the python-gitlab object for now (legacy compatibility)
        # We might want to refactor compliance_mode.py later, but for now passing .client works
        render_compliance_mode(client.client)

    elif mode == "User Profile Overview":
        st.subheader("👤 User Profile Overview")
        user_input = st.text_input("Enter Username", placeholder="username")

        if user_input:
            with st.spinner(f"Finding user '{user_input}'..."):
                user_info = users.get_user_by_username(client, user_input)

            if user_info:
                render_user_profile(client, user_info)
            else:
                 st.error(f"User '{user_input}' not found.")

    elif mode == "Batch 2026 ICFAI":
        render_batch_mode_ui(client, "ICFAI")

    elif mode == "Batch 2026 RCTS":
        render_batch_mode_ui(client, "RCTS")
>>>>>>> origin/feature-final

if __name__ == "__main__":
    main()
