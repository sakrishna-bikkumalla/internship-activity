import datetime

import pandas as pd
import streamlit as st

from gitlab_compliance_checker.infrastructure.gitlab import batch
from gitlab_compliance_checker.ui.csv_common import map_row_to_member, render_csv_upload_section


@st.cache_data(ttl=3600)
def cached_process_batch_users(_client, usernames_tuple, project_ids=None):
    """Cache the unified batch results for 1 hour."""
    return batch.process_batch_users(_client, list(usernames_tuple), project_ids=project_ids)


def render_batch_analytics_ui(client):
    st.subheader("📊 Batch Analytics")
    st.caption("Comprehensive report combining General Stats, Authored Issue Quality, and Assigned MR Quality.")

    # 1. Configuration Section
    with st.expander("🛠️ Configuration", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            try:
                csv_rows = render_csv_upload_section(key="batch_roster_upload")
            except Exception as e:
                st.error(f"Error reading uploaded CSV file: {e}")
                csv_rows = []

        with col2:
            text_input = st.text_area(
                "⌨️ Enter Usernames & Colleges (one per line)",
                height=200,
                placeholder="user1, college name\nuser2, college name\nuser3, college name\n.........",
                help="Format: 'username' or 'username, college name' — one entry per line.",
            )

        st.markdown("#### 📂 Filter by Project Repos *(optional)*")
        st.caption(
            "Filter results to specific GitLab project paths (e.g. `group/repo-name`). Leave blank for all projects."
        )
        repo_input = st.text_area(
            "Project Repo Paths",
            height=100,
            placeholder="tools/gitlab-compliance-checker\ngroup/another-repo",
            key="batch_repo_input",
        )
        repo_paths = [line.strip() for line in repo_input.splitlines() if line.strip()]

    # 2. Execution
    btn_label = "🚀 Run Unified Analysis"
    if st.button(btn_label, type="primary", width="stretch"):
        # username -> college name mapping (populated from both text input and CSV)
        college_map: dict[str, str] = {}

        # Parse text area: each line is "username" or "username, college"
        usernames: list[str] = []
        for line in text_input.splitlines():
            line_str: str = line.strip()
            if not line_str:
                continue
            if "," in line_str:
                parts = line_str.split(",", 1)
                uname = parts[0].strip()
                college = parts[1].strip()
            else:
                uname = line_str
                college = ""
            if uname:
                usernames.append(uname)
                college_map[uname.lower()] = college

        # Also add parsed CSV entries
        if csv_rows:
            for row in csv_rows:
                member = map_row_to_member(row)
                uname = member.get("username")
                if uname:
                    usernames.append(uname)
                    # CSV entries take precedence over text-area entries for same username
                    college_map[uname.lower()] = member.get("college", "")

        # Deduplicate and sort
        usernames = sorted(set(usernames))

        if not usernames:
            st.warning("Please enter at least one username or upload a file.")
            return

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
            results = cached_process_batch_users(client, tuple(usernames), project_ids=project_ids)

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
                row["Issue Total (Auth)"] = is_q.get(
                    "Total Assigned", 0
                )  # This is actually Total Authored because of the filter in batch.py
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
        st.dataframe(df, width="stretch")

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
