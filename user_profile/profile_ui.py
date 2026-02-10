import streamlit as st
from gitlab import GitlabGetError

from user_profile.profile_service import (
    check_profile_readme,
    get_user_groups_count,
    get_user_profile,
    get_user_issues_details,
    get_user_issues_list,
    get_user_open_mrs_count,
    get_user_projects_count,
)


def render_user_profile(gl):
    st.subheader("👤 User Profile Overview")

    username = st.text_input(
        "Enter GitLab username, user ID, or profile URL",
        placeholder="e.g. SandhyaRani_111",
    )

    if st.button("Fetch User Info & Check README"):

        if not username:
            st.warning("Please enter a username.")
            return

        try:
            # ---------------- Fetch User ----------------
            user = get_user_profile(gl, username)
            if not user:
                st.error("User not found.")
                return

            st.markdown(f"### User: {user.name} (@{user.username}, ID: {user.id})")
            st.markdown(f"[View GitLab Profile]({user.web_url})")

            # ---------------- Account Statistics ----------------
            st.subheader("📊 Account Statistics")

            issue_data = get_user_issues_details(gl, user.id)

            col1, col2 = st.columns(2)
            col3, col4 = st.columns(2)

            projects_count = get_user_projects_count(gl, user.id)
            groups_count = get_user_groups_count(gl, user.id)
            open_issues_count = issue_data.get("open", 0)
            open_mrs_count = get_user_open_mrs_count(gl, user.id)

            col1.metric("Projects", projects_count)
            col2.metric("Open Issues", open_issues_count)
            col3.metric("Groups", groups_count)
            col4.metric("Open MRs", open_mrs_count)

            # ---------------- Issues Summary ----------------
            st.subheader("🐞 Issues Summary")

            col1, col2, col3 = st.columns(3)
            col4, col5 = st.columns(2)

            col1.metric("Total Issues", issue_data["total"])
            col2.metric("Open Issues", issue_data["open"])
            col3.metric("Closed Issues", issue_data["closed"])

            col4.metric("Today Morning Issues", issue_data["today_morning"])
            col5.metric("Today Afternoon Issues", issue_data["today_afternoon"])

            # ---------------- Detailed Issues Table ----------------
            st.subheader("📋 Detailed Issues")
            issues = get_user_issues_list(gl, user.id, limit=200)

            if issues:
                st.dataframe(issues, use_container_width=True)
            else:
                st.info("No issues found for this user.")

            # ---------------- Profile README Status ----------------
            st.subheader("📄 Profile README Status")

            readme_status = check_profile_readme(gl, user.username)

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

        except GitlabGetError as e:
            st.error(f"GitLab API Error: {str(e)}")
