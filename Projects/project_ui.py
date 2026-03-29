import streamlit as st

from .file_classifier import classify_files
from .license_checker import check_license
from .readme_checker import check_readme
from .templates_checker import check_templates


def get_project_compliance(gl, project_id: int) -> dict:
    """Run available project compliance checks and return a combined result."""
    return {
        "readme": check_readme(gl, project_id),
        "license": check_license(gl, project_id),
        "templates": check_templates(gl, project_id),
        "file_types": classify_files(gl, project_id),
    }


def render_project_compliance(gl, project_id: int):
    st.subheader("📦 Project Compliance Report")

    results = get_project_compliance(gl, project_id)

    col1, col2 = st.columns(2)

    with col1:
        st.metric("README", results["readme"]["status"])
        st.metric("LICENSE", results["license"]["status"])

    with col2:
        st.metric("Templates", results["templates"]["status"])

    st.markdown("### 📂 File Classification")
    st.json(results["file_types"])


def render_project_section(gitlab_url: str, gitlab_token: str):
    """Main Streamlit section for project compliance checks."""
    st.subheader("📦 Project Compliance")

    project_ref = st.text_input(
        "Enter Project ID or Full Path",
        placeholder="e.g. 12345 or group/subgroup/project",
    )

    if not st.button("Run Project Compliance"):
        return

    if not project_ref.strip():
        st.warning("Please enter a valid project ID or path.")
        return

    try:
        import gitlab

        gl = gitlab.Gitlab(gitlab_url, private_token=gitlab_token)
        proj = gl.projects.get(project_ref.strip())
        render_project_compliance(gl, proj.id)
    except Exception as e:
        st.error(f"Failed to fetch project/report: {e}")
