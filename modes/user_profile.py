import pandas as pd
import streamlit as st

from gitlab_utils import commits, groups, issues, merge_requests, projects


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

    # Fetch Data
    with st.spinner("Fetching comprehensive user data..."):
        # 1. Projects
        proj_data = projects.get_user_projects(client, user_id, username)

        # 2. Commits - Passing full simple_user_info
        all_projs = proj_data["all"]
        all_commits, commit_counts, commit_stats = commits.get_user_commits(
            client, simple_user_info, all_projs
        )

        verified_contributed = []
        for p in proj_data["contributed"]:
            if commit_counts.get(p["id"], 0) > 0:
                verified_contributed.append(p)

        personal_projects = proj_data["personal"]

        # 3. Groups
        user_groups = groups.get_user_groups(client, user_id)

        # 4. MRs
        user_mrs, mr_stats = merge_requests.get_user_mrs(client, user_id)

        # 5. Issues
        user_issues, issue_stats = issues.get_user_issues(client, user_id)

    # --- Display ---

    # Projects
    st.markdown("---")
    st.subheader("📦 Projects")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.metric("Personal Projects", len(personal_projects))
        if personal_projects:
            with st.expander("View Personal Projects"):
                for p in personal_projects:
                    st.write(f"- [{p['name_with_namespace']}]({p['web_url']})")
    with p_col2:
        st.metric("Contributed Projects", len(verified_contributed))
        if verified_contributed:
            with st.expander("View Contributed Projects"):
                for p in verified_contributed:
                    st.write(f"- [{p['name_with_namespace']}]({p['web_url']})")

    # Commits
    st.markdown("---")
    st.subheader("💻 Commits Analysis (IST)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Commits", commit_stats["total"])
    c2.metric("Morning (9:30-12:30)", commit_stats["morning_commits"])
    c3.metric("Afternoon (2:00-5:00)", commit_stats["afternoon_commits"])

    if all_commits:
        with st.expander("View Recent Commits"):
            # Use pandas for table
            df_commits = pd.DataFrame(all_commits)
            # Display updated columns
            st.dataframe(
                df_commits[["project_name", "message", "date", "time", "slot"]], width="stretch"
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
                df_mrs[
                    ["title", "role", "state", "desc_score", "quality", "feedback", "created_at"]
                ],
                width="stretch",
            )

    st.markdown("---")
    st.subheader("🔍 MR Compliance (Live API)")
    with st.spinner(f"Fetching Live MR Compliance API for {name}..."):
        project_ids_to_check = [p["id"] for p in personal_projects] + [
            p["id"] for p in verified_contributed
        ]
        live_stats, prob_mrs = merge_requests.get_single_user_live_mr_compliance(
            client, project_ids_to_check, name
        )

        avg_desc_score = 0
        total_eval = live_stats.get("Total MRs Evaluated", 0)
        if total_eval > 0:
            avg_desc_score = int(live_stats.get("Total Desc Score", 0) / total_eval)

        st.markdown(f"**Average MR Description Quality:** {avg_desc_score}/100")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("No Description", live_stats.get("No Description", 0))
        c2.metric("No Time Spent", live_stats.get("No Time Spent", 0))
        c3.metric("No Issues Linked", live_stats.get("No Issues Linked", 0))
        c4.metric("No Unit Tests", live_stats.get("No Unit Tests", 0))
        c5.metric("Failed Pipelines", live_stats.get("Failed Pipelines", 0))

        st.markdown("### ⚠️ Non-Compliant Merge Requests")
        if prob_mrs:
            df_prob = pd.DataFrame(prob_mrs)

            # Map boolean compliance values to professional color indicators
            bool_cols = [
                "No Description",
                "No Time Spent",
                "No Issues Linked",
                "No Unit Tests",
                "Failed Pipeline",
            ]
            for col in bool_cols:
                if col in df_prob.columns:
                    df_prob[col] = df_prob[col].map(
                        {True: "✅", False: "", "True": "✅", "False": ""}
                    )

            st.dataframe(
                df_prob[
                    [
                        "Title",
                        "State",
                        "No Description",
                        "No Time Spent",
                        "No Issues Linked",
                        "No Unit Tests",
                        "Failed Pipeline",
                    ]
                ],
                width="stretch",
            )
        else:
            st.success("All analyzed Merge Requests are compliant!")

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
            st.dataframe(df_issues[["title", "state", "created_at"]], width="stretch")
