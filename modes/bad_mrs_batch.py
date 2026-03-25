"""
bad_mrs_batch.py
~~~~~~~~~~~~~~~~
Streamlit UI for the "BAD MRs (Batch)" mode.

Fetches MR data for all 34 users concurrently using ThreadPoolExecutor.
Single endpoint per user: GET /merge_requests?author_id=<id>&scope=all

Columns: Username | Closed MRs | No Desc | Improper Desc | No Issues
         | No Time Spent | No Unit Tests | Failed Pipeline
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from gitlab_utils.async_bad_mrs import BATCH_USERNAMES, fetch_all_bad_mrs


def render_bad_mrs_batch_ui(client) -> None:
    st.subheader("🚨 BAD MRs – Batch Analysis")

    with st.expander(f"📋 Batch Users ({len(BATCH_USERNAMES)} total)", expanded=False):
        st.code("\n".join(BATCH_USERNAMES), language="text")

    if st.button("⚡ Generate Report", key="_bad_mrs_generate", type="primary"):
        if not client or not client.client:
            st.error("GitLab client not initialized. Check URL and Token in the sidebar.")
            return

        with st.spinner(
            f"⏳ Performing High-Accuracy Analysis for {len(BATCH_USERNAMES)} users... This may take 1-3 minutes to stay within GitLab's rate limits."
        ):
            try:
                rows = fetch_all_bad_mrs(client, BATCH_USERNAMES)
            except Exception as exc:
                st.error(f"Error during batch fetch: {exc}")
                return

        df = pd.DataFrame(rows)

        # ── Summary metrics ──────────────────────────────────────────────────
        total_closed = int(df["Closed MRs"].sum())

        col1, col2 = st.columns(2)
        col1.metric("Total Closed MRs", total_closed)
        col2.metric("Total Users", len(df))

        # ── Results table ────────────────────────────────────────────────────
        st.markdown("### 📋 BAD MR Count per User")
        st.caption("Sorted by Username. Metrics include across all Closed MRs.")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ── Excel export ─────────────────────────────────────────────────────
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="BAD MRs by User")

                summary_data = {
                    "Metric": [
                        "Total Closed MRs",
                        "Total Users",
                        "Total No Desc",
                        "Total Improper Desc",
                        "Total No Issues",
                        "Total No Time Spent",
                        "Total No Unit Tests",
                        "Total Failed Pipeline",
                        "Total No Semantic Commits",
                        "Total No Internal Review",
                        "Total Merge > 2 Days",
                        "Total Merge > 1 Week",
                    ],
                    "Count": [
                        total_closed,
                        len(df),
                        int(df["No Desc"].sum()),
                        int(df["Improper Desc"].sum()),
                        int(df["No Issues"].sum()),
                        int(df["No Time Spent"].sum()),
                        int(df["No Unit Tests"].sum()),
                        int(df["Failed Pipeline"].sum()),
                        int(df["No Semantic Commits"].sum()),
                        int(df["No Internal Review"].sum()),
                        int(df["Merge > 2 Days"].sum()),
                        int(df["Merge > 1 Week"].sum()),
                    ],
                }
                pd.DataFrame(summary_data).to_excel(writer, index=False, sheet_name="Summary")

            st.download_button(
                label="📥 Download bad_mrs_report.xlsx",
                data=output.getvalue(),
                file_name="bad_mrs_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="_bad_mrs_download",
                type="secondary",
            )
        except Exception as exc:
            st.error(f"Error generating Excel file: {exc}")

    # --- Single User Fetch Section ---
    st.markdown("---")
    st.subheader("👤 Single User Fetch")
    st.caption("Fetch BAD MR metrics for a single user not in the batch.")

    col1, col2 = st.columns([3, 1])
    single_user = col1.text_input("Enter GitLab Username", key="_bad_mrs_single_user", placeholder="e.g. john_doe")
    fetch_clicked = col2.button("🔍 Fetch User", key="_bad_mrs_single_fetch", use_container_width=True)

    if fetch_clicked and single_user:
        if not client or not client.client:
            st.error("GitLab client not initialized.")
            return

        single_user = single_user.strip()
        with st.spinner(f"⏳ Analyzing MRs for '{single_user}'..."):
            try:
                # fetch_all_bad_mrs takes a list of usernames
                results = fetch_all_bad_mrs(client, [single_user])
                if results:
                    res = results[0]
                    st.success(f"Analysis complete for {single_user}!")

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Closed MRs", res["Closed MRs"])
                    m2.metric("No Desc", res["No Desc"])
                    m3.metric("Improper Desc", res["Improper Desc"])
                    m4.metric("No Issues", res["No Issues"])

                    m5, m6, m7 = st.columns(3)
                    m5.metric("No Time Spent", res["No Time Spent"])
                    m6.metric("No Unit Tests", res["No Unit Tests"])
                    m7.metric("Failed Pipeline", res["Failed Pipeline"])

                    m8, m9, m10 = st.columns(3)
                    m8.metric("No Semantic Commits", res["No Semantic Commits"])
                    m9.metric("No Internal Review", res["No Internal Review"])
                    m10.metric("Merge > 2 Days", res["Merge > 2 Days"])

                    m11, _, _ = st.columns(3)
                    m11.metric("Merge > 1 Week", res["Merge > 1 Week"])

                    # Also show as a small dataframe for consistency
                    st.dataframe(pd.DataFrame([res]), use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No data found for user '{single_user}'.")
            except Exception as exc:
                st.error(f"Error fetching data for {single_user}: {exc}")
    elif fetch_clicked and not single_user:
        st.warning("Please enter a username first.")
