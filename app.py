import streamlit as st
from dotenv import load_dotenv
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

    mode = st.sidebar.radio(
        "Select Mode",
        [
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


if __name__ == "__main__":
    main()
