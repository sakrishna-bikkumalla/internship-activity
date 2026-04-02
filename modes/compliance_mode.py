import concurrent.futures

import streamlit as st

from gitlab_utils.projects import extract_path_from_url, get_project_with_retries
from Projects.compliance_service import get_dx_suggestions, run_project_compliance_checks


@st.cache_data(ttl=60)
def cached_get_project(_gl_client, path_or_id):
    """Cached wrapper for get_project_with_retries."""
    return get_project_with_retries(_gl_client, path_or_id)


def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


def render_compliance_mode(gl_client):
    st.subheader("🔍 Project Compliance Analysis")

    tabs = st.tabs(["Single Project", "Batch Projects"])

    with tabs[0]:
        st.markdown("#### Check a Single Project")

        # Step 1: Input Project
        project_input = st.text_input(
            "Enter Project ID or URL", placeholder="https://gitlab.com/group/project", key="single_project_input"
        )

        col1, col2 = st.columns([1, 2])

        with col1:
            fetch_project = st.button("Fetch Project & Branches", key="fetch_project_btn")

        # Step 2: Branch Selection (Intermediate Stage)
        if fetch_project or st.session_state.get("current_project_id") == project_input:
            try:
                if fetch_project:
                    with st.spinner("Fetching branches..."):
                        pid = extract_path_from_url(project_input)
                        project = cached_get_project(gl_client, pid)
                        st.session_state["current_project_obj"] = project
                        st.session_state["current_project_id"] = project_input
                        st.session_state["project_branches"] = get_project_branches(project)

                project = st.session_state.get("current_project_obj")
                branches = st.session_state.get("project_branches", [])

                if project:
                    st.success(f"Project found: **{project.name_with_namespace}**")

                    default_branch = getattr(project, "default_branch", "main")
                    default_idx = branches.index(default_branch) if default_branch in branches else 0

                    selected_branch = st.selectbox(
                        "Select Branch for Analysis",
                        options=branches,
                        index=default_idx,
                        key="selected_branch_dropdown",
                    )

                    if st.button("Run Compliance Analysis", key="run_analysis_single"):
                        with st.spinner(f"Analyzing branch '{selected_branch}'..."):
                            report = run_project_compliance_checks(gl_client, project.id, ref=selected_branch)

                            # --- UI Rendering ---
                            m_col1, m_col2, m_col3 = st.columns(3)
                            m_col1.metric("Compliance Score", f"{report.get('dx_score', 0)}%")
                            m_col2.metric("Stack", report.get("tools", {}).get("project_type", "Unknown"))
                            m_col3.metric("AGPLv3 Compliance", "✅" if report["license"].get("valid") else "❌")

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
                                if report.get("dx_ci"):
                                    st.markdown("---")
                                    from Projects.project_ui import render_dx_ci_pipeline_ui

                                    render_dx_ci_pipeline_ui(report["dx_ci"])
                            with d_tabs[4]:
                                sugs = get_dx_suggestions(report)
                                for s in sugs:
                                    st.warning(f"**{s['item']}**: {s['reason']}\n\n*Action:* {s['action']}")
            except Exception as e:
                st.error(f"Error: {e}")
                if "current_project_id" in st.session_state:
                    del st.session_state["current_project_id"]

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
                project = cached_get_project(gl_client, pid)
                report = run_project_compliance_checks(gl_client, project.id)

                return {
                    "Project": project.name_with_namespace,
                    "Compliance Score": f"{report.get('dx_score', 0)}%",
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
            st.write("### 📊 Batch Compliance Summary")
            st.dataframe(results)
