import concurrent.futures
from urllib.parse import urlparse

import streamlit as st
from gitlab import GitlabGetError

from Projects.compliance_service import get_dx_suggestions, run_project_compliance_checks


@st.cache_data(ttl=60)
def get_project_with_retries(gl_client, path_or_id):
    try:
        return gl_client.projects.get(int(path_or_id) if str(path_or_id).isdigit() else path_or_id)
    except GitlabGetError:
        raise


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


def render_compliance_mode(gl_client):
    st.subheader("🔍 Production-Grade DX Analysis")

    tabs = st.tabs(["Single Project", "Batch Projects"])

    with tabs[0]:
        st.markdown("#### Check a Single Project")
        project_input = st.text_input(
            "Enter Project ID or URL", placeholder="https://gitlab.com/group/project", key="single_project_input"
        )

        if st.button("Run Ultimate Analysis", key="run_analysis_single"):
            if project_input:
                try:
                    with st.spinner("Analyzing project..."):
                        pid = extract_path_from_url(project_input)
                        project = get_project_with_retries(gl_client, pid)
                        report = run_project_compliance_checks(gl_client, project.id)

                        # --- UI Rendering ---
                        col1, col2, col3 = st.columns(3)
                        col1.metric("DX Score", f"{report.get('dx_score', 0)}%")
                        col2.metric("Stack", report.get("tools", {}).get("project_type", "Unknown"))
                        col3.metric("AGPLv3", "✅" if report["license"].get("valid") else "❌")

                        # Tabs for details
                        d_tabs = st.tabs(["Tools & Quality", "Security", "Testing", "Automation", "Suggestions"])
                        with d_tabs[0]:
                            st.json(report["tools"]["quality_tools"])
                        with d_tabs[1]:
                            st.json(report["tools"]["security"])
                        with d_tabs[2]:
                            st.json(report["tools"]["testing"])
                        with d_tabs[3]:
                            st.json(report["tools"]["automation"])
                        with d_tabs[4]:
                            sugs = get_dx_suggestions(report)
                            for s in sugs:
                                st.warning(f"**{s['item']}**: {s['reason']}\n\n*Action:* {s['action']}")
                except Exception as e:
                    st.error(f"Error: {e}")

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
            try:
                pid = extract_path_from_url(line)
                project = get_project_with_retries(gl_client, pid)
                report = run_project_compliance_checks(gl_client, project.id)

                return {
                    "Project": project.name_with_namespace,
                    "Score": f"{report.get('dx_score', 0)}%",
                    "Stack": report.get("tools", {}).get("project_type", "Unknown"),
                    "AGPLv3": "✅" if report["license"].get("valid") else "❌",
                    "Security": "✅" if report["tools"]["security"].get("secret_scanning") else "❌",
                    "Coverage": "✅" if report["tools"]["testing"].get("coverage") else "❌",
                    "CI/CD": "✅" if report["tools"]["automation"].get("gitlab_ci") else "❌",
                    "Pre-commit": "✅" if report["tools"]["automation"].get("pre_commit") else "❌",
                }
            except Exception as e:
                return {"Project": line, "Error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_line = {executor.submit(_process_line, line): line for line in lines}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_line)):
                results.append(future.result())
                progress_bar.progress((i + 1) / len(lines))

        if results:
            st.write("### 📊 Ultimate Batch Summary")
            st.dataframe(results)
