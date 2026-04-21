import datetime
import io

import pandas as pd
import streamlit as st

from gitlab_compliance_checker.infrastructure.gitlab import batch


@st.cache_data(ttl=3600)
def cached_process_batch_users(_client, usernames_tuple, project_ids=None):
    """Cache the unified batch results for 1 hour."""
    return batch.process_batch_users(_client, list(usernames_tuple), project_ids=project_ids)


def _parse_uploaded_user_csv(uploaded_file) -> tuple[list[str], dict[str, str]]:
    """Extract usernames and optional college values from an uploaded CSV."""
    uploaded_file.seek(0)
    csv_df = pd.read_csv(uploaded_file)
    csv_df.columns = [str(col).strip() for col in csv_df.columns]

    lowered = {str(col).strip().lower(): col for col in csv_df.columns}
    username_col = next(
        (lowered[key] for key in ("username", "gitlab username", "gitlab_username", "user", "user name", "user_name") if key in lowered),
        None,
    )
    college_col = next(
        (
            lowered[key]
            for key in (
                "college",
                "college name",
                "college_name",
                "institution",
                "institution name",
                "institution_name",
                "university",
                "university name",
                "organization",
                "organisation",
                "org",
                "school",
            )
            if key in lowered
        ),
        None,
    )

    if username_col is None:
        uploaded_file.seek(0)
        csv_df = pd.read_csv(uploaded_file, header=None)
        username_col = csv_df.columns[0]
        college_col = csv_df.columns[1] if len(csv_df.columns) > 1 else None

    usernames: list[str] = []
    # Keys are stored lowercase for case-insensitive lookup later
    college_map: dict[str, str] = {}

    for _, csv_row in csv_df.iterrows():
        uname = str(csv_row.get(username_col, "")).strip() if pd.notna(csv_row.get(username_col, "")) else ""
        college = (
            str(csv_row.get(college_col, "")).strip()
            if college_col is not None and pd.notna(csv_row.get(college_col, ""))
            else ""
        )
        if uname:
            usernames.append(uname)
            college_map[uname.lower()] = college

    return usernames, college_map


def render_batch_analytics_ui(client):
    st.subheader("📊 Batch Analytics")
    st.caption("Comprehensive report combining General Stats, Authored Issue Quality, and Assigned MR Quality.")

    # 1. Configuration Section
    with st.expander("🛠️ Configuration", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            uploaded_file = st.file_uploader(
                "📂 Upload Usernames & Colleges (.csv)",
                type=["csv"],
                help="CSV with a 'username' column and an optional 'college' (or 'institution'/'university') column. "
                     "If no header, column 1 = username, column 2 = college.",
            )

        with col2:
            text_input = st.text_area(
                "⌨️ Enter Usernames & Colleges (one per line)",
                height=200,
                placeholder="user1, College Name\nuser2, Another College\nuser3",
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
    if st.button(btn_label, type="primary", use_container_width=True):
        # username -> college name mapping (populated from both text input and CSV)
        college_map: dict[str, str] = {}

        # Parse text area: each line is "username" or "username, college"
        usernames: list[str] = []
        for line in text_input.splitlines():
            line = line.strip()
            if not line:
                continue
            if "," in line:
                parts = line.split(",", 1)
                uname = parts[0].strip()
                college = parts[1].strip()
            else:
                uname = line
                college = ""
            if uname:
                usernames.append(uname)
                college_map[uname.lower()] = college

        # Also parse uploaded CSV
        if uploaded_file is not None:
            try:
                uploaded_usernames, uploaded_college_map = _parse_uploaded_user_csv(uploaded_file)
                usernames.extend(uploaded_usernames)
                # CSV entries take precedence over text-area entries for the same username
                college_map.update(uploaded_college_map)
            except Exception as e:
                st.error(f"Error reading uploaded CSV file: {e}")

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

        # Excel download
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Unified_Report")

            st.download_button(
                label="📥 Download Unified Report (Excel)",
                data=output.getvalue(),
                file_name=f"Unified_Batch_Report_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as e:
            st.error(f"Error creating Excel: {e}")
