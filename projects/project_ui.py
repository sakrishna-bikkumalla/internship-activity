import streamlit as st
from projects.compliance_checks import check_project_compliance
from projects.classification import classify_repository_files
from reports.export import reports_to_csv, reports_to_excel
from gitlab_utils.network import get_project_with_retries


def _render_report(report):
    st.success(
        f"Compliance Score: **{report.get('score_pct', 0)}%** "
        f"({report.get('passed', 0)}/{report.get('total', 0)} checks passed)"
    )

    checks = report.get("checks", [])
    if checks:
        st.dataframe(checks, use_container_width=True)

        csv_bytes = reports_to_csv(checks)
        xlsx_bytes = reports_to_excel(checks)

        c1, c2 = st.columns(2)
        c1.download_button(
            "Download CSV",
            data=csv_bytes,
            file_name=f"compliance_{report.get('project_id', 'report')}.csv",
            mime="text/csv",
        )
        c2.download_button(
            "Download Excel",
            data=xlsx_bytes,
            file_name=f"compliance_{report.get('project_id', 'report')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_project_compliance_ui(gl=None, report=None, project=None, branch=None, classification=None):
    st.subheader("📋 Compliance Summary")

    if gl is None:
        st.info("Project compliance UI is loading. Configure GitLab URL/token in sidebar.")
        return

    project_input = st.text_input(
        "Project ID or path",
        placeholder="e.g. 1234 or group/subgroup/project-name",
        help="Provide GitLab numeric project ID or full path with namespace.",
    )
    branch_input = st.text_input("Branch (optional)", value="")

    if st.button("Run Compliance Check", type="primary"):
        if not project_input.strip():
            st.warning("Please enter project ID/path first.")
            return

        try:
            project = get_project_with_retries(gl, project_input.strip())
            report = check_project_compliance(project, branch=branch_input.strip() or None)
            classification = classify_repository_files(report.get("file_paths", []))

            st.markdown(
                f"**Project:** `{report.get('project_path') or report.get('project_name')}`  \n"
                f"**Branch:** `{report.get('branch')}`"
            )

            _render_report(report)

            st.subheader("🗂️ Repository Classification")
            st.json({k: len(v) for k, v in (classification or {}).items()})

        except Exception as exc:
            st.error(f"Failed to fetch compliance report: {exc}")
