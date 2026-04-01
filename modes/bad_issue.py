"""
bad_issue.py
~~~~~~~~~~~~
Streamlit UI for the "BAD Issues (Batch)" mode.

Fetches Issue data for all 34 users concurrently using ThreadPoolExecutor.
Single endpoint per user: GET /issues?assignee_id=<id>&scope=all

Columns: Username | Closed Issues | No Desc | No Labels
         | No Milestone | No Time Spent | Long Open Time (>2 days)
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from gitlab_utils.client import BATCH_USERNAMES


@st.cache_data(ttl=3600)
def cached_batch_evaluate_issues(_client, usernames_tuple):
    """Cache the batch issue evaluation results for 1 hour."""
    return _client.batch_evaluate_issues(list(usernames_tuple), issue_scope="assignee")


@st.cache_data(ttl=3600)
def cached_single_user_issues(_client, username):
    """Cache single user issue evaluation results for 1 hour."""
    return _client.batch_evaluate_issues([username], issue_scope="assignee")


def render_bad_issue_batch_ui(client) -> None:
    st.subheader("🐛 BAD Issues – Batch Analysis")

    with st.expander(f"📋 Batch Users ({len(BATCH_USERNAMES)} total)", expanded=False):
        st.code("\n".join(BATCH_USERNAMES), language="text")

    if st.button("⚡ Generate Report", key="_bad_issues_generate", type="primary"):
        if not client or not client.client:
            st.error("GitLab client not initialized. Check URL and Token in the sidebar.")
            return

        with st.spinner(
            f"⏳ Performing High-Accuracy Analysis for {len(BATCH_USERNAMES)} users... This may take 1-3 minutes to stay within GitLab's rate limits."
        ):
            try:
                rows = cached_batch_evaluate_issues(client, tuple(BATCH_USERNAMES))
            except Exception as exc:
                st.error(f"Error during batch fetch: {exc}")
                return

        df = pd.DataFrame(rows)

        # ── Summary metrics ──────────────────────────────────────────────────
        total_assigned = int(df["Total Assigned"].sum())
        total_opened = int(df["Opened Issues"].sum())
        total_closed = int(df["Closed Issues"].sum())

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Assigned", total_assigned)
        col2.metric("Total Opened", total_opened)
        col3.metric("Total Closed", total_closed)
        col4.metric("Total Users", len(df))

        # ── Results table ────────────────────────────────────────────────────
        st.markdown("### 📋 BAD Issue Count per User")
        st.caption("Sorted by Username. Metrics include across all Closed Issues.")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ── Excel export ─────────────────────────────────────────────────────
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="BAD Issues by User")

                summary_data = {
                    "Metric": [
                        "Total Assigned",
                        "Total Opened",
                        "Total Closed Issues",
                        "Total Users",
                        "Total No Desc",
                        "Total No Labels",
                        "Total No Milestone",
                        "Total No Time Spent",
                        "Total Long Open Time (>2 days)",
                        "Total No Semantic Title",
                    ],
                    "Count": [
                        total_assigned,
                        total_opened,
                        total_closed,
                        len(df),
                        int(df["No Desc"].sum()),
                        int(df["No Labels"].sum()),
                        int(df["No Milestone"].sum()),
                        int(df["No Time Spent"].sum()),
                        int(df["Long Open Time (>2 days)"].sum()),
                        int(df["No Semantic Title"].sum()),
                    ],
                }
                pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Summary")

            st.download_button(
                label="📥 Download bad_issues_report.xlsx",
                data=output.getvalue(),
                file_name="bad_issues_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="_bad_issues_download",
                type="secondary",
            )
        except Exception as exc:
            st.error(f"Error generating Excel file: {exc}")

    # --- Single User Fetch Section ---
    st.markdown("---")
    st.subheader("👤 Single User Fetch")
    st.caption("Fetch BAD Issue metrics for a single user based on assigned issues.")

    col1, col2 = st.columns([3, 1])
    single_user = col1.text_input("Enter GitLab Username", key="_bad_issues_single_user", placeholder="e.g. john_doe")
    fetch_clicked = col2.button("🔍 Fetch User", key="_bad_issues_single_fetch", use_container_width=True)

    if fetch_clicked and single_user:
        if not client or not client.client:
            st.error("GitLab client not initialized.")
            return

        single_user = single_user.strip()
        with st.spinner(f"⏳ Analyzing Issues for '{single_user}'..."):
            try:
                # batch_evaluate_issues takes a list of usernames
                results = cached_single_user_issues(client, single_user)
                if results:
                    res = results[0]
                    st.success(f"Analysis complete for {single_user}!")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Assigned", res["Total Assigned"])
                    m2.metric("Opened Issues", res["Opened Issues"])
                    m3.metric("Closed Issues", res["Closed Issues"])
                    m4.metric("No Desc", res["No Desc"])

                    m5, m6, m7, m8 = st.columns(4)
                    m5.metric("No Labels", res["No Labels"])
                    m6.metric("No Milestone", res["No Milestone"])
                    m7.metric("No Time Spent", res["No Time Spent"])
                    m8.metric("Long Open Time (>2 days)", res["Long Open Time (>2 days)"])

                    m9, _, _ = st.columns(3)
                    m9.metric("No Semantic Title", res["No Semantic Title"])

                    # Also show as a small dataframe for consistency
                    st.dataframe(pd.DataFrame([res]), use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No data found for user '{single_user}'.")
            except Exception as exc:
                st.error(f"Error fetching data for {single_user}: {exc}")
    elif fetch_clicked and not single_user:
        st.warning("Please enter a username first.")
