import streamlit as st

from .compliance_service import get_dx_suggestions, run_project_compliance_checks


def render_project_compliance(gl, project_id: int):
    st.subheader("📦 Production-Grade DX Analysis")

    with st.spinner("Deep analysis of tools, CI/CD, and quality gates..."):
        report = run_project_compliance_checks(gl, project_id)

    # --- Summary Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("DX Score", f"{report.get('dx_score', 0)}%")
    with col2:
        lang = report.get("tools", {}).get("project_type", "Unknown")
        st.metric("Stack", lang)
    with col3:
        license_valid = report["license"].get("valid")
        st.metric("AGPLv3 Compliance", "✅ Yes" if license_valid else "❌ No")
    with col4:
        readme_status = "⚠️ Improved Needed" if report["readme"].get("needs_improvement") else "✅ Excellent"
        st.metric("Documentation", readme_status)

    # --- Categorized Analysis ---
    tabs = st.tabs(["🛠 Quality & Tools", "🔒 Security", "🧪 Testing", "🤖 Automation & CI", "📝 Metadata"])

    with tabs[0]:
        st.markdown("#### Code Quality & Typing")
        tools = report.get("tools", {}).get("quality_tools", {})
        for tool, present in tools.items():
            st.write(f"{'✅' if present else '❌'} **{tool.title()}**")

    with tabs[1]:
        st.markdown("#### Security Enforcement")
        sec = report.get("tools", {}).get("security", {})
        st.write(f"{'✅' if sec.get('secret_scanning') else '❌'} **Secret Scanning** (Gitleaks/TruffleHog)")
        st.write(f"{'✅' if sec.get('dependency_audit') else '❌'} **Dependency Audit** (uv audit/npm audit)")
        if "bandit" in sec:
            st.write(f"{'✅' if sec.get('bandit') else '❌'} **Static Analysis** (Bandit)")

    with tabs[2]:
        st.markdown("#### Test Coverage & Thresholds")
        test = report.get("tools", {}).get("testing", {})
        st.write(f"{'✅' if test.get('pytest') or test.get('jest_vitest') else '❌'} **Test Framework**")
        st.write(f"{'✅' if test.get('coverage') else '❌'} **Coverage Reporting**")
        st.write(f"{'✅' if test.get('coverage_threshold') else '🔍'} **Enforced Thresholds** (fail-under)")

    with tabs[3]:
        st.markdown("#### CI/CD & Automation")
        auto = report.get("tools", {}).get("automation", {})
        st.write(f"{'✅' if auto.get('gitlab_ci') else '❌'} **GitLab CI Pipeline**")
        st.write(f"{'✅' if auto.get('pre_commit') else '❌'} **Pre-commit Hooks**")
        st.write(f"{'✅' if auto.get('git_cliff') else '❌'} **Automated Changelog** (Git-Cliff)")

    with tabs[4]:
        st.markdown("#### Project Metadata & Tags")
        meta = report.get("metadata", {})
        st.write(f"{'✅' if meta.get('description_present') else '❌'} **Description**")
        st.write(f"{'✅' if meta.get('tags_present') else '❌'} **Git Tags**")

    # --- Actionable Suggestions ---
    st.markdown("---")
    st.markdown("### 📌 Actionable DX Suggestions")
    suggestions = get_dx_suggestions(report)
    if not suggestions:
        st.success("Your project DX is absolutely perfect! No suggestions.")
    else:
        for sug in suggestions:
            with st.expander(f"❌ {sug['item']} — {sug['reason']}"):
                st.markdown(f"**How to fix:** {sug['action']}")


def render_project_section(gitlab_url: str, gitlab_token: str):
    """Main Streamlit section for project compliance checks."""
    st.subheader("📦 Ultimate Project Compliance")

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
