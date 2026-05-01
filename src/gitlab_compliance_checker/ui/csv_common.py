import pandas as pd
import streamlit as st

from gitlab_compliance_checker.services.weekly_performance.models import (
    InternCSVRow,
    parse_intern_csv,
)


def render_csv_upload_section(
    key: str,
    label: str = "📂 Upload Roster (.csv)",
    description: str | None = None,
    help_text: str | None = None,
) -> list[InternCSVRow]:
    """
    Renders a standardized CSV uploader with an example preview and returns parsed rows.

    Args:
        key: Unique Streamlit key for the file uploader.
        label: Label for the file uploader.
        description: Optional markdown string to display above the uploader.
        help_text: Optional custom help text for the uploader tooltip.

    Returns:
        List of parsed dictionaries, or an empty list if no file uploaded/error occurred.
    """
    if description:
        st.markdown(description)

    if not help_text:
        help_text = (
            "Standard CSV Fields: Team Name (optional), Name, Gitlab_username, Gitlab_email, "
            "Corpus_username, Global_username, Global_email, Date_of_joining, College name"
        )

    # 1. Renders the uploader
    uploaded_file = st.file_uploader(
        label,
        type=["csv"],
        key=key,
        help=help_text,
    )

    # 2. Renders the standardized sample preview
    sample_df = pd.DataFrame(
        [
            {
                "Team Name": "Backend",
                "Name": "John Doe",
                "Gitlab_username": "john123",
                "Gitlab_email": "john@org.com",
                "Corpus_username": "john_c",
                "Global_username": "EXT001",
                "Global_email": "john.doe@global.com",
                "Date_of_joining": "2024-01-01",
                "College name": "Example University",
            }
        ]
    )
    st.caption("Standard CSV Format Guide:")
    st.dataframe(sample_df, hide_index=True, width="stretch")

    # 3. Parse and return if file exists
    if uploaded_file:
        try:
            # Important: seek(0) to ensure we read from start if called multiple times
            uploaded_file.seek(0)
            content = uploaded_file.read()
            rows = parse_intern_csv(content)
            if rows:
                st.success(f"✅ Successfully parsed {len(rows)} users from **{uploaded_file.name}**")
                return rows
            else:
                st.warning("No valid data found in the uploaded CSV.")
        except Exception as e:
            st.error(f"Error parsing CSV: {e}")

    return []


def map_row_to_member(row: InternCSVRow) -> dict:
    """
    Standardizes an InternCSVRow for UI modules (converts internal keys to UI keys).

    Standard UI Keys:
    - name, username, email, college, corpus_username, global_username, global_email, date_of_joining
    """
    return {
        "name": row.get("name", ""),
        "username": row.get("gitlab_username", ""),
        "email": row.get("gitlab_email", ""),
        "college": row.get("college_name", ""),
        "corpus_username": row.get("corpus_username", ""),
        "global_username": row.get("global_username", ""),
        "global_email": row.get("global_email", ""),
        "date_of_joining": row.get("date_of_joining", ""),
    }


def group_by_team(rows: list[InternCSVRow]) -> dict[str, list[dict]]:
    """Groups standardized member rows by team name."""
    teams_map: dict[str, list[dict]] = {}
    for row in rows:
        member = map_row_to_member(row)
        tname = row.get("team_name") or "Default Team"
        if tname not in teams_map:
            teams_map[tname] = []
        teams_map[tname].append(member)
    return teams_map
