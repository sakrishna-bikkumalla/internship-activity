from io import BytesIO

import pandas as pd
import streamlit as st

from gitlab_compliance_checker.infrastructure.gitlab import batch
from gitlab_compliance_checker.services.profile.profile_service import check_profile_readme


def render_user_profile(client, simple_user_info):
    """
    Renders the User Profile UI.
    """
    if not simple_user_info:
        st.error("User info not provided.")
        return

    user_id = simple_user_info.get("id")
    username = simple_user_info.get("username")
    name = simple_user_info.get("name")
    avatar_url = simple_user_info.get("avatar_url")
    web_url = simple_user_info.get("web_url")

    # Header
    col1, col2 = st.columns([1, 4])
    with col1:
        if avatar_url:
            st.image(avatar_url, width=100)
    with col2:
        st.markdown(f"### {name} (@{username})")
        st.markdown(f"**ID:** {user_id} | [GitLab Profile]({web_url})")

    # Fetch Data concurrently via the batch engine
    with st.spinner("Fetching comprehensive user data in parallel..."):
        user_data = batch.process_single_user(client, username)

    if not user_data or user_data.get("status") != "Success":
        error_msg = user_data.get("error", "Unknown error") if user_data else "Unknown error"
        st.error(f"Error fetching data: {error_msg}")
        return

    # Extract data from the resulting dict
    data = user_data["data"]
    proj_data = data["projects"]
    all_commits = data["commits"]
    commit_stats = data["commit_stats"]
    user_groups = data["groups"]
    user_mrs = data["mrs"]
    mr_stats = data["mr_stats"]
    user_issues = data["issues"]
    issue_stats = data["issue_stats"]

    # Projects classification
    personal_projects = proj_data["personal"]
    verified_contributed = proj_data["contributed"]

    # --- Display ---

    # Projects
    st.markdown("---")
    st.subheader("📦 Projects")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.metric("Personal Projects", len(personal_projects))
        if personal_projects:
            with st.expander("View Personal Projects"):
                df_pers = pd.DataFrame(personal_projects)
                st.dataframe(
                    df_pers[["name_with_namespace", "web_url"]],
                    column_config={
                        "name_with_namespace": "Project Name",
                        "web_url": st.column_config.LinkColumn("Link", display_text="View Repo"),
                    },
                    hide_index=True,
                    width="stretch",
                    height=350,
                )
    with p_col2:
        st.metric("Contributed Projects", len(verified_contributed))
        if verified_contributed:
            with st.expander("View Contributed Projects"):
                df_cont = pd.DataFrame(verified_contributed)
                st.dataframe(
                    df_cont[["name_with_namespace", "web_url"]],
                    column_config={
                        "name_with_namespace": "Project Name",
                        "web_url": st.column_config.LinkColumn("Link", display_text="View Repo"),
                    },
                    hide_index=True,
                    width="stretch",
                    height=350,
                )

    # Commits
    st.markdown("---")
    st.subheader("💻 Commits Analysis (IST)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Commits", commit_stats["total"])
    c2.metric("Morning (9:00-12:29)", commit_stats["morning_commits"])
    c3.metric("Afternoon (12:30-5:00)", commit_stats["afternoon_commits"])

    if all_commits:
        with st.expander("View Recent Commits"):
            # Use pandas for table
            df_commits = pd.DataFrame(all_commits)
            # Display updated columns, including web_url rendered as a link
            st.dataframe(
                df_commits[["project_name", "message", "date", "time", "slot", "web_url"]],
                column_config={"web_url": st.column_config.LinkColumn("Commit Link", display_text="View Commit")},
                width="stretch",
            )

    # Groups
    st.markdown("---")
    st.subheader("👥 Groups")
    if user_groups:
        st.write(f"**Total Groups:** {len(user_groups)}")
        df_groups = pd.DataFrame(user_groups)
        st.dataframe(df_groups, width="stretch")
    else:
        st.info("No groups found.")

    # Merge Requests
    st.markdown("---")
    st.subheader("🔀 Merge Requests")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total MRs", mr_stats["total"])
    m2.metric("Merged", mr_stats["merged"])
    m3.metric("Open/Pending", mr_stats["opened"])
    m4.metric("Closed", mr_stats["closed"])

    if user_mrs:
        with st.expander("View MR Details"):
            df_mrs = pd.DataFrame(user_mrs)
            st.dataframe(
                df_mrs[["title", "role", "state", "created_at", "web_url"]],
                column_config={"web_url": st.column_config.LinkColumn("MR Link", display_text="View MR")},
                width="stretch",
            )

    # Issues
    st.markdown("---")
    st.subheader("⚠️ Issues")
    i1, i2, i3 = st.columns(3)
    i1.metric("Total Issues", issue_stats["total"])
    i2.metric("Open", issue_stats["opened"])
    i3.metric("Closed", issue_stats["closed"])

    if user_issues:
        with st.expander("View Issue Details"):
            df_issues = pd.DataFrame(user_issues)
            st.dataframe(
                df_issues[["title", "role", "state", "created_at", "web_url"]],
                column_config={"web_url": st.column_config.LinkColumn("Issue Link", display_text="View Issue")},
                width="stretch",
            )

    # ---------------- Profile README Status ----------------
    st.markdown("---")
    st.subheader("📄 Profile README Status")

    # Using the underlying python-gitlab client from our custom client
    readme_status = check_profile_readme(client.client, username)

    if readme_status["exists"]:
        st.success("✅ Profile README is set up correctly!")
        if readme_status.get("url"):
            st.markdown(f"[View README]({readme_status['url']})")
    else:
        st.error("❌ No profile project found (i.e., <username>/<username>).")
        st.info(
            "💡 Suggestion: Create a README for your profile by following these steps:\n\n"
            "1. Create a new project with the **exact same name as your username**\n"
            "2. Add a **README.md** file in that project\n"
            "3. This README will appear on your GitLab profile page"
        )

    # Excel Export
    try:
        export_payload = {
            "Personal_Projects": personal_projects,
            "Contributed_Projects": verified_contributed,
            "Commits": all_commits,
            "Groups": user_groups,
            "MergeRequests": user_mrs,
            "Issues": user_issues,
        }

        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            for sheet_name, sheet_rows in export_payload.items():
                if sheet_rows:
                    pd.DataFrame(sheet_rows).to_excel(writer, index=False, sheet_name=sheet_name[:31])

        st.markdown("---")
        st.download_button(
            label="Download Full User Report (Excel)",
            data=output.getvalue(),
            file_name=f"{username}_profile_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.info(f"Excel export unavailable: {e}")
