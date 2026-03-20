"""
bad_mrs_batch.py
~~~~~~~~~~~~~~~~
Streamlit UI for the "BAD MRs (Batch)" mode.

Fetches MR data for all 34 users concurrently using ThreadPoolExecutor.
Single endpoint per user: GET /merge_requests?author_id=<id>&scope=all

Columns: Username | Closed MRs
         | No Description | Improper Description | No Issues Linked
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
        st.caption("Sorted by Closed MRs (most active first).")
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
                        "Total No Description",
                        "Total Improper Description",
                        "Total No Issues Linked",
                        "Total No Time Spent",
                        "Total No Unit Tests",
                        "Total Failed Pipeline",
                    ],
                    "Count": [
                        total_closed,
                        len(df),
                        int(df["No Description"].sum()),
                        int(df["Improper Description"].sum()),
                        int(df["No Issues Linked"].sum()),
                        int(df["No Time Spent"].sum()),
                        int(df["No Unit Tests"].sum()),
                        int(df["Failed Pipeline"].sum()),
                    ],
                }
                pd.DataFrame(summary_data).to_excel(
                    writer, index=False, sheet_name="Summary"
                )

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
