import datetime

import pandas as pd
import streamlit as st

from gitlab_compliance_checker.infrastructure.gitlab import batch
from gitlab_compliance_checker.services.roster_service import get_all_members_with_teams


@st.cache_data(ttl=3600)
def cached_process_batch_users(_client, usernames_tuple, project_ids=None, overrides=None):
    """Cache the unified batch results for 1 hour."""
    return batch.process_batch_users(_client, list(usernames_tuple), project_ids=project_ids, overrides=overrides)


def render_batch_analytics_ui(client):
    st.subheader("📊 Batch Analytics")
    st.caption("Comprehensive report combining General Stats, Authored Issue Quality, and Assigned MR Quality.")

    # 1. Fetch Users from Database
    db_members = get_all_members_with_teams()
    if not db_members:
        st.warning("⚠️ No interns found in the Roster Database. Please add users in the Admin panel first.")
        return

    # Map for easy selection
    # format: "Name (username)"
    user_options = {f"{m['name']} (@{m['gitlab_username']})": m for m in db_members}

    # 2. Configuration Section
    with st.expander("🛠️ Selection & Configuration", expanded=True):
        selection_options = ["All Registered Interns", "Select Specific Interns"]
        if st.session_state.get("fetched_group_members"):
            selection_options.append("Select from Group Names")

        selection_mode = st.radio(
            "Target Selection",
            selection_options,
            horizontal=True,
            help="Choose whether to analyze everyone in the roster or just a few.",
        )

        selected_members = []
        member_overrides = {}
        if selection_mode == "All Registered Interns":
            selected_members = db_members
            st.info(f"📍 Analysis will include all **{len(db_members)}** interns from the database.")
        elif selection_mode == "Select from Group Names":
            group_members = st.session_state.get("fetched_group_members", [])
            group_user_options = {f"{m['name']} (@{m['username']})": m for m in group_members}
            selected_group_labels = st.multiselect(
                "Select Group Members", options=list(group_user_options.keys()), default=[]
            )
            for label in selected_group_labels:
                m = group_user_options[label]
                username = m["username"]
                selected_members.append(
                    {"gitlab_username": username, "name": m["name"], "college_name": "Group Member"}
                )
                member_overrides[username] = {
                    "override_email": m.get("email"),
                    "override_username": m.get("username"),
                }
        else:
            selected_labels = st.multiselect("Select Interns", options=list(user_options.keys()), default=[])
            selected_members = [user_options[label] for label in selected_labels]

        st.markdown("#### 📂 Filter by Project Repos *(optional)*")
        st.caption(
            "Filter results to specific GitLab project paths (e.g. `group/repo-name`). Leave blank for all projects."
        )
        repo_input = st.text_area(
            "Project Repo Paths",
            height=80,
            placeholder="tools/gitlab-compliance-checker\ngroup/another-repo",
            key="batch_repo_input",
        )
        repo_paths = [line.strip() for line in repo_input.splitlines() if line.strip()]

    # 3. Execution
    btn_label = f"🚀 Run Analysis for {len(selected_members)} User(s)"
    if st.button(btn_label, type="primary", use_container_width=True):
        if not selected_members:
            st.warning("Please select at least one intern.")
            return

        usernames = sorted([m["gitlab_username"] for m in selected_members])
        college_map = {m["gitlab_username"].lower(): m.get("college_name", "") for m in selected_members}

        project_ids = None
        if repo_paths:
            with st.spinner(f"Resolving {len(repo_paths)} project repo(s)…"):
                resolved_ids, failed_paths = batch.resolve_project_paths(client, repo_paths)

            if failed_paths:
                st.warning(
                    f"⚠️ Could not resolve {len(failed_paths)} repo path(s): "
                    + ", ".join(f"`{p}`" for p in failed_paths)
                )
            if resolved_ids:
                st.info(f"✅ Filtering by **{len(resolved_ids)}** project(s)")
                project_ids = resolved_ids
            else:
                st.error("None of the entered repo paths could be resolved.")
                return

        st.info(f"Processing {len(usernames)} users...")
        with st.spinner("Fetching unified data in parallel..."):
            results = cached_process_batch_users(
                client, tuple(usernames), project_ids=project_ids, overrides=member_overrides
            )

        st.success("Unified Batch processing complete!")

        # Prepare Data for Display & Export
        report_data = []
        for res in results:
            u = res.get("username")
            status = res.get("status")
            err = res.get("error", "")
            data = res.get("data", {})

            # 1. Identity & Status
            row = {
                "Username": u,
                "College": college_map.get(u.lower(), ""),
                "Status": status,
            }

            if status == "Success":
                # 2. General Stats
                projects_info = data.get("projects", {})
                c_stats = data.get("commit_stats", {"total": 0, "morning_commits": 0, "afternoon_commits": 0})

                row["Commits Total"] = c_stats["total"]
                row["Commits Morning"] = c_stats["morning_commits"]
                row["Commits Afternoon"] = c_stats["afternoon_commits"]
                row["Projects (Auth)"] = len(projects_info.get("personal", []))
                row["Projects (Contr)"] = len(projects_info.get("contributed", []))
                row["Groups Count"] = len(data.get("groups", []))

                # 3. MR Quality (Authored)
                mr_q = data.get("mr_quality", {})
                row["MR Total (Authored)"] = mr_q.get("Closed MRs", 0)
                row["MR No Desc"] = mr_q.get("No Desc", 0)
                row["MR No Issues"] = mr_q.get("No Issues", 0)
                row["MR No Time"] = mr_q.get("No Time Spent", 0)
                row["MR Failed Pipe"] = mr_q.get("Failed Pipeline", 0)
                row["MR No Semantic"] = mr_q.get("No Semantic Commits", 0)
                row["MR No Review"] = mr_q.get("No Internal Review", 0)
                row["MR > 2 Days"] = mr_q.get("Merge > 2 Days", 0)
                row["MR > 1 Week"] = mr_q.get("Merge > 1 Week", 0)

                # 4. Issue Quality (Authored)
                is_q = data.get("issue_quality", {})
                row["Issue Total (Auth)"] = is_q.get("Total Assigned", 0)
                row["Issue Closed"] = is_q.get("Closed Issues", 0)
                row["Issue No Desc"] = is_q.get("No Desc", 0)
                row["Issue No Labels"] = is_q.get("No Labels", 0)
                row["Issue No Milestone"] = is_q.get("No Milestone", 0)
                row["Issue No Time"] = is_q.get("No Time Spent", 0)
                row["Issue Long Open"] = is_q.get("Long Open Time (>2 days)", 0)
                row["Issue No Semantic"] = is_q.get("No Semantic Title", 0)
            else:
                row["Error"] = err

            report_data.append(row)

        df = pd.DataFrame(report_data)
        st.dataframe(df, use_container_width=True)

        # Export
        today = datetime.date.today()

        # CSV download
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Unified Report (CSV)",
            data=csv_bytes,
            file_name=f"Unified_Batch_Report_{today}.csv",
            mime="text/csv",
        )
