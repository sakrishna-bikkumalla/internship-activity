import datetime

import pandas as pd
import streamlit as st

from gitlab_compliance_checker.infrastructure.gitlab import batch
from gitlab_compliance_checker.services.roster_service import (
    get_all_batches,
    get_all_members_with_teams,
    get_members_by_team,
    get_teams_by_batch,
)


@st.cache_data(ttl=3600)
def cached_process_batch_users(_client, usernames_tuple, project_ids=None, overrides=None):
    """Cache the unified batch results for 1 hour."""
    return batch.process_batch_users(_client, list(usernames_tuple), project_ids=project_ids, overrides=overrides)


def _init_ba_state():
    """Initialize session state for Compliance Audit filtering."""
    defaults = {
        "_ba_selected_batch": "All Batches",
        "_ba_selected_teams": ["All Teams"],
        "_ba_selected_members": ["All Members"],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_batch_analytics_ui(client):
    _init_ba_state()

    db_members = get_all_members_with_teams()
    if not db_members:
        st.warning("⚠️ No interns found in the Roster Database. Please add users in the Admin panel first.")
        return

    # --- Hierarchical Filtering ---
    batches = get_all_batches()
    batch_names = ["All Batches"] + [b["name"] for b in batches]

    with st.expander("🎯 Filter Selection", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            selected_batch = st.selectbox(
                "Select Batch",
                options=batch_names,
                index=batch_names.index(st.session_state["_ba_selected_batch"])
                if st.session_state["_ba_selected_batch"] in batch_names
                else 0,
                key="_ba_batch_sel_widget",
                help="Select the batch of interns to analyze.",
            )
            if selected_batch != st.session_state["_ba_selected_batch"]:
                st.session_state["_ba_selected_batch"] = selected_batch
                st.session_state["_ba_selected_teams"] = ["All Teams"]
                st.session_state["_ba_selected_members"] = ["All Members"]
                st.rerun()

        teams_in_batch = get_teams_by_batch(selected_batch)
        team_options = ["All Teams"] + sorted([t["name"] for t in teams_in_batch])

        with c2:
            selected_teams = st.multiselect(
                "Select Team(s)",
                options=team_options,
                default=st.session_state["_ba_selected_teams"]
                if all(t in team_options for t in st.session_state["_ba_selected_teams"])
                else ["All Teams"],
                key="_ba_teams_sel_widget",
                help="Select specific teams within the batch.",
            )
            if selected_teams != st.session_state["_ba_selected_teams"]:
                st.session_state["_ba_selected_teams"] = selected_teams
                st.rerun()

        # Determine members to show in the third filter based on team selection
        if "All Teams" in selected_teams:
            filtered_members_for_sel = (
                db_members
                if selected_batch == "All Batches"
                else [m for t in teams_in_batch for m in get_members_by_team(t["name"], selected_batch)]
            )
        else:
            filtered_members_for_sel = [
                m for t_name in selected_teams for m in get_members_by_team(t_name, selected_batch)
            ]

        all_potential_members = sorted({f"{m['name']} (@{m['gitlab_username']})" for m in filtered_members_for_sel})
        member_options = ["All Members"] + all_potential_members

        with c3:
            selected_members_labels = st.multiselect(
                "Select Individual(s)",
                options=member_options,
                default=st.session_state["_ba_selected_members"]
                if all(m in member_options for m in st.session_state["_ba_selected_members"])
                else ["All Members"],
                key="_ba_members_sel_widget",
                help="Select specific individuals.",
            )
            if selected_members_labels != st.session_state["_ba_selected_members"]:
                st.session_state["_ba_selected_members"] = selected_members_labels
                st.rerun()

    # Final member list for analysis
    if "All Members" in selected_members_labels:
        selected_members = filtered_members_for_sel
    else:
        selected_members = [
            m
            for label in selected_members_labels
            for m in filtered_members_for_sel
            if f"{m['name']} (@{m['gitlab_username']})" == label
        ]

    # 2. Project Filter
    member_overrides = {}
    repo_paths = []

    with st.expander("📂 Optional Project Filter", expanded=False):
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

            if status == "Error":
                row["Compliance %"] = 0
                row["Error Details"] = err
                report_data.append(row)
                continue

            # 2. Compliance Metrics
            pc = data.get("project_compliance", {})
            row["Compliance %"] = pc.get("Compliance Rate", 0)
            row["Total Projects"] = pc.get("Total Projects", 0)
            row["Compliant"] = pc.get("Compliant", 0)

            # 3. MR Quality
            mrq = data.get("merge_request_quality", {})
            row["MR Merged"] = mrq.get("Total Merged", 0)
            row["Avg Merge Days"] = mrq.get("Avg Merge Time", 0)
            row["MR No Desc"] = mrq.get("No Desc", 0)
            row["MR No Labels"] = mrq.get("No Labels", 0)
            row["MR No Time"] = mrq.get("No Time Spent", 0)
            row["MR Slow (>2d)"] = mrq.get("Merge > 2 Days", 0)

            # 4. Issue Quality
            isq = data.get("issue_quality", {})
            row["Issues Closed"] = isq.get("Closed Issues", 0)
            row["Issue No Desc"] = isq.get("No Desc", 0)
            row["Issue No Labels"] = isq.get("No Labels", 0)
            row["Issue No Time"] = isq.get("No Time Spent", 0)

            report_data.append(row)

        df = pd.DataFrame(report_data)

        # UI Display
        st.subheader("📊 Analytical Results")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Download
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name=f"batch_analytics_{datetime.date.today()}.csv",
            mime="text/csv",
        )
