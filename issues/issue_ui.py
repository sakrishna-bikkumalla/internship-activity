"""UI rendering for issue-related compliance information.

This module handles all Streamlit-based rendering for issues.
Pure business logic should be in issue_service.py and issue_metrics.py.
"""


import streamlit as st


def render_issue_compliance_ui(report, classification=None):
    """Render issue-related compliance information in the UI.

    Args:
        report (dict): Compliance report containing issue template information
        classification (dict, optional): File classification result
    """
    st.markdown("#### 📋 Issue & Merge Request Templates")

    col1, col2 = st.columns(2)

    with col1:
        issue_templates_exists = report.get("issue_templates_folder", False)
        issue_files = report.get("issue_template_files", [])

        emoji = "✅" if issue_templates_exists else "❌"
        st.markdown(f"{emoji} **Issue Templates Folder**")
        if issue_templates_exists:
            st.write(f"Found {len(issue_files)} template(s):")
            for file in sorted(issue_files):
                st.markdown(f"  - `{file}`")
        else:
            st.write("Not found in `.gitlab/issue_templates/`")

    with col2:
        mr_templates_exists = report.get("merge_request_templates_folder", False)
        mr_files = report.get("merge_request_template_files", [])

        emoji = "✅" if mr_templates_exists else "❌"
        st.markdown(f"{emoji} **Merge Request Templates Folder**")
        if mr_templates_exists:
            st.write(f"Found {len(mr_files)} template(s):")
            for file in sorted(mr_files):
                st.markdown(f"  - `{file}`")
        else:
            st.write("Not found in `.gitlab/merge_request_templates/`")


def render_issue_suggestions(report):
    """Render suggestions for missing or incomplete issue templates.

    Args:
        report (dict): Compliance report containing issue template information
    """
    issue_templates_exists = report.get("issue_templates_folder", False)
    mr_templates_exists = report.get("merge_request_templates_folder", False)

    if not issue_templates_exists or not mr_templates_exists:
        st.markdown("#### 📌 Issue & MR Template Suggestions")

        if not issue_templates_exists:
            st.markdown(
                """❌ **Issue templates folder missing**

Create `.gitlab/issue_templates/` and add template files like:
- `Bug.md` – For bug reports
- `Feature.md` – For feature requests
- `Documentation.md` – For documentation improvements
- `Default.md` – Fallback template

**Quick Template Example:**
```markdown
## Description
[Describe the issue here]

## Steps to Reproduce
1. [First step]
2. [Second step]
3. [...]

## Expected Result
[What should happen]

## Actual Result
[What actually happens]
```
"""
            )

        if not mr_templates_exists:
            st.markdown(
                """❌ **Merge Request templates folder missing**

Create `.gitlab/merge_request_templates/` and add templates like:
- `Bug.md` – For bug fixes
- `Feature.md` – For new features
- `Documentation.md` – For doc updates
- `Default.md` – Fallback template

**Quick Template Example:**
```markdown
## Description
[Describe what this MR does]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
[Describe the tests you ran]

## Checklist
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
```
"""
            )

        try:
            st.image(
                "assets/files.png",
                caption="Recommended file structure inside `.gitlab/` directory",
                width=500,
            )
        except Exception:
            pass


def render_issue_metrics_ui(metrics):
    """Render issue metrics dashboard.

    Args:
        metrics (dict): Metrics calculated from issue counts
    """
    st.markdown("#### 📊 Issue Metrics")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Open Issues",
            metrics.get("open_issues", 0),
        )

    with col2:
        st.metric(
            "Assigned Issues",
            metrics.get("assigned_issues", 0),
        )

    with col3:
        st.metric(
            "Unassigned Issues",
            metrics.get("unassigned_issues", 0),
        )

    # Show assignment health
    assignment_pct = metrics.get("assignment_percentage", 0)
    st.markdown(f"**Assignment Health**: {assignment_pct}%")

    # Visual indicator
    if assignment_pct >= 90:
        st.success("✅ Excellent assignment coverage")
    elif assignment_pct >= 70:
        st.info("🟢 Good assignment coverage")
    elif assignment_pct >= 50:
        st.warning("🟡 Fair assignment coverage")
    else:
        st.error("🔴 Low assignment coverage")


def render_issue_summary_card(summary):
    """Render a summary card for issue compliance.

    Args:
        summary (dict): Issue compliance summary
    """
    score = summary.get("compliance_score", 0)

    # Determine color based on score
    if score >= 85:
        color = "#00d084"  # Green
        label = "Excellent"
    elif score >= 70:
        color = "#a3e635"  # Yellow-green
        label = "Good"
    elif score >= 50:
        color = "#fbbf24"  # Amber
        label = "Fair"
    else:
        color = "#ef4444"  # Red
        label = "Poor"

    # Create custom progress bar HTML
    progress_html = f"""
    <div style="margin: 10px 0;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <span style="font-weight: bold;">Issue Compliance Score</span>
            <span style="font-weight: bold; color: {color};">{score}/100 ({label})</span>
        </div>
        <div style="width: 100%; height: 25px; background-color: #e5e7eb; border-radius: 5px; overflow: hidden; border: 1px solid #d1d5db;">
            <div style="height: 100%; width: {score}%; background-color: {color}; transition: width 0.3s ease;"></div>
        </div>
    </div>
    """
    st.markdown(progress_html, unsafe_allow_html=True)

    # Show compliance details
    with st.expander("Compliance Details"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Templates**")
            st.markdown(
                f"✅ Issue Templates: {summary.get('has_issue_templates', False)}"
            )
            st.markdown(
                f"✅ MR Templates: {summary.get('has_mr_templates', False)}"
            )

        with col2:
            st.markdown("**Metrics**")
            metrics = summary.get("metrics", {})
            st.markdown(f"📊 Open: {metrics.get('open_issues', 0)}")
            st.markdown(f"✔️ Assigned: {metrics.get('assigned_issues', 0)}")
