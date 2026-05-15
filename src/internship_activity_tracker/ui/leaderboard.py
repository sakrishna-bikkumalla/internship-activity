"""
Batch Analytics and Ranking Mode — Dynamic Team Creation + Edit
------------------------------------------------------
Supports creating and editing teams via UI with full session state persistence.
Fetches analytics via process_batch_users() and renders a ranked ranking table.

Score formula:
    score = (total_commits * 1) + (merged_mrs * 5) + (total_mrs * 2) + (issues_closed * 3)

Session state keys (all prefixed _lb_ except "teams" and "edit_team_index"):
    "teams"                   — master list of saved team dicts
    "edit_team_index"         — int index of team being edited, or None
    "_lb_show_create_form"    — bool, whether create-form is expanded
    "_lb_draft_members"       — member list being built before first Save
    "_lb_edit_draft"          — copy of team being edited (name, project, members)
    "_lb_triggered"           — bool, whether Run Analysis has been clicked
"""

import copy
import datetime
import io
import statistics
from html import escape
from pathlib import Path
from typing import Any

import dateutil.parser
import pandas as pd
import streamlit as st

from internship_activity_tracker.infrastructure.corpus.client import CorpusClient
from internship_activity_tracker.infrastructure.gitlab.batch import (
    fetch_batch_commits,
    process_batch_users_no_commits,
)
from internship_activity_tracker.infrastructure.gitlab.timelogs import format_time_spent
from internship_activity_tracker.services.roster_service import (
    get_all_batches,
    get_all_teams_with_members,
    get_members_by_team,
    get_teams_by_batch,
)

# ---------------------------------------------------------------------------
# Default Teams (loaded from data/teams.json)
# ---------------------------------------------------------------------------


# Removed _load_default_teams - now using database


# ---------------------------------------------------------------------------
# Session State Bootstrap
# ---------------------------------------------------------------------------


def _init_state() -> None:
    """Initialise all session-state keys used by this module. Safe to call repeatedly."""
    if st.session_state.get("_lb_page") != "Workspace":  # Only reload if not already analyzed or if forced
        st.session_state["teams"] = get_all_teams_with_members()

    defaults: dict = {
        "edit_team_index": None,
        "_lb_show_create_form": False,
        "_lb_show_upload_form": False,
        "_lb_draft_members": [],
        "_lb_edit_draft": {},
        "_lb_triggered": False,
        "_lb_date_since": None,  # ISO 8601 UTC string or None
        "_lb_date_until": None,  # ISO 8601 UTC string or None
        "_lb_from_date": None,  # date input value or None
        "_lb_to_date": None,  # date input value or None
        "_lb_clear_dates_requested": False,  # one-shot flag to clear date widgets safely
        "_lb_project_id": None,  # Resolved int or None
        "_lb_project_input": "",  # Raw string input
        "_lb_selected_batch": "All Batches",
        "_lb_selected_teams": ["All Teams"],
        "_lb_selected_members": ["All Members"],
        "_lb_page": "Workspace",
        "_lb_last_ranking_rows": [],
        "_lb_cached_results": None,
        "_lb_last_filters": None,
        "_lb_corpus_token": None,
        "_lb_corpus_client": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ---------------------------------------------------------------------------
# Corpus Login
# ---------------------------------------------------------------------------


def _render_corpus_login() -> None:
    """Render a Corpus login widget in the sidebar (same pattern as Weekly Performance Tracker)."""
    with st.sidebar.expander("Corpus Login", expanded=st.session_state.get("_lb_corpus_token") is None):
        phone = st.text_input("Phone", key="_lb_corpus_phone", placeholder="+1234567890")
        password = st.text_input("Password", key="_lb_corpus_password", type="password")
        if st.button("Login to Corpus", key="_lb_corpus_login_btn"):
            if not phone or not password:
                st.warning("Phone and password are required.")
            else:
                try:
                    corpus_client = CorpusClient()
                    token = corpus_client.login(phone, password)
                    st.session_state["_lb_corpus_token"] = token
                    st.session_state["_lb_corpus_client"] = corpus_client
                    st.success("Logged in to Corpus!")
                except Exception as e:
                    st.error(f"Login failed: {e}")


# ---------------------------------------------------------------------------
# Corpus Media Fetch
# ---------------------------------------------------------------------------


def _fetch_corpus_media_for_team(
    corpus_client: "CorpusClient",
    team_members: list[dict],
    since: str | None = None,
    until: str | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Fetch ALL corpus media (audio, image, video, file) for each team member.

    Args:
        corpus_client: Authenticated CorpusClient instance.
        team_members:  List of member dicts (must contain 'username' and 'corpus_username').
        since:         ISO date string YYYY-MM-DD for start filter (optional).
        until:         ISO date string YYYY-MM-DD for end filter (optional).

    Returns:
        Dict mapping gitlab_username -> { "audio": [...], "image": [...], "video": [...], "file": [...] }
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)
    result: dict[str, dict[str, list[dict]]] = {}

    for member in team_members:
        gl_username = member.get("username", "")
        corpus_uid = member.get("corpus_username", "").strip()
        if not corpus_uid:
            _log.debug(f"[LB Corpus] No corpus_username for {gl_username}, skipping")
            result[gl_username] = {"audio": [], "image": [], "video": [], "file": []}
            continue

        try:
            records = corpus_client.fetch_records(corpus_uid, start_date=since, end_date=until)
            media = corpus_client.extract_all_media(records)
            result[gl_username] = media
            total = sum(len(v) for v in media.values())
            _log.debug(f"[LB Corpus] {gl_username} ({corpus_uid}): {total} files fetched")
        except Exception as exc:
            _log.warning(f"[LB Corpus] Failed for {gl_username} ({corpus_uid}): {exc}")
            result[gl_username] = {"audio": [], "image": [], "video": [], "file": []}

    return result


# ---------------------------------------------------------------------------
# Pure Logic Helpers
# ---------------------------------------------------------------------------


def _render_date_filter() -> tuple[str | None, str | None]:
    """
    Render the date range filter UI.
    Returns (since_iso, until_iso) — both are ISO 8601 UTC strings or None.
    Shows an active filter badge; provides a Clear Filter button.
    """
    import datetime as _dt

    st.markdown("### 📅 Date Range Filter")
    col_from, col_to, col_clear = st.columns([2, 2, 1])

    with col_from:
        from_date = st.date_input(
            "From Date",
            value=None,
            key="_lb_from_date",
            help="Leave blank to fetch full history",
        )
    with col_to:
        to_date = st.date_input(
            "To Date",
            value=None,
            key="_lb_to_date",
            help="Leave blank to fetch full history",
        )
    with col_clear:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✖ Clear Filter", key="_lb_clear_dates"):
            st.session_state["_lb_date_since"] = None
            st.session_state["_lb_date_until"] = None
            st.session_state["_lb_triggered"] = False
            st.rerun()

    since_iso: str | None = None
    until_iso: str | None = None

    if from_date and to_date:
        if from_date > to_date:
            st.warning("⚠️  **From Date** must be before or equal to **To Date**.")
        else:
            # Convert to UTC ISO 8601 covering the full calendar days
            utc = _dt.timezone.utc
            since_iso = _dt.datetime.combine(from_date, _dt.time.min, tzinfo=utc).isoformat()
            until_iso = _dt.datetime.combine(to_date, _dt.time.max, tzinfo=utc).isoformat()

            st.info(
                f"🗓 Filtering from **{from_date}** to **{to_date}** (UTC).  "
                "Commits, MRs and Issues will be scoped to this range."
            )
    elif from_date or to_date:
        st.warning("Select both **From Date** and **To Date** to apply a filter.")
    else:
        st.caption("No date filter applied — showing full history.")

    # Persist to session_state so it survives reruns
    st.session_state["_lb_date_since"] = since_iso
    st.session_state["_lb_date_until"] = until_iso

    st.divider()
    return since_iso, until_iso


def _calculate_score(total_commits: int, merged_mrs: int, total_mrs: int, issues_closed: int) -> int:
    """Return individual productivity score."""
    return total_commits * 1 + merged_mrs * 5 + total_mrs * 2 + issues_closed * 3


def _extract_member_row(result: dict) -> dict:
    """Flatten one process_batch_users() result into display metrics. Handles errors gracefully."""
    username = result.get("username", "unknown")
    status = result.get("status", "Error")
    if status != "Success":
        return {
            "Username": username,
            "Status": status,
            "Total Commits": 0,
            "Morning Commits": 0,
            "Afternoon Commits": 0,
            "MR Created": 0,
            "MR Merged": 0,
            "MR Open": 0,
            "MR Closed": 0,
            "MR Assigned": 0,
            "Issues Raised": 0,
            "Issues Closed": 0,
            "Issues Assigned": 0,
            "Groups": 0,
            "Score": 0,
            "Time Spent": "0 min",
            "time_spent_seconds": 0,
            "mrs_open_time": 0,
            "mrs_merged_time": 0,
            "issues_open_time": 0,
            "issues_closed_time": 0,
            "Error": result.get("error", "Unknown error"),
            "commits_list": [],
            "item_time_breakdown": [],
        }

    data = result.get("data", {})
    c = data.get("commit_stats", {})
    m = data.get("mr_stats", {})
    i = data.get("issue_stats", {})

    total_commits = c.get("total", 0)
    total_mrs = m.get("total", 0)
    merged_mrs = m.get("merged", 0)
    issues_closed = i.get("closed", 0)

    total_time_seconds = data.get("total_time_spent_seconds", 0)

    return {
        "Username": username,
        "Status": status,
        "Total Commits": total_commits,
        "Morning Commits": c.get("morning_commits", 0),
        "Afternoon Commits": c.get("afternoon_commits", 0),
        "MR Created": total_mrs,
        "MR Merged": merged_mrs,
        "MR Open": m.get("opened", 0),
        "MR Closed": m.get("closed", 0),
        "MR Assigned": m.get("assigned", 0),
        "Issues Raised": i.get("total", 0),
        "Issues Closed": issues_closed,
        "Issues Assigned": i.get("assigned", 0),
        "Groups": len(data.get("groups", [])),
        "Score": _calculate_score(total_commits, merged_mrs, total_mrs, issues_closed),
        "Time Spent": format_time_spent(total_time_seconds),
        "time_spent_seconds": total_time_seconds,
        "mrs_open_time": data.get("time_breakdown", {}).get("mrs_open", 0),
        "mrs_merged_time": data.get("time_breakdown", {}).get("mrs_merged", 0),
        "issues_open_time": data.get("time_breakdown", {}).get("issues_open", 0),
        "issues_closed_time": data.get("time_breakdown", {}).get("issues_closed", 0),
        "mrs_list": data.get("mrs", []),
        "issues_list": data.get("issues", []),
        "commits_list": data.get("commits", []),
        "item_time_breakdown": data.get("item_time_breakdown", []),
    }


def _aggregate_team_totals(member_rows: list[dict]) -> dict:
    """Sum numeric metric columns across all member rows."""
    totals: dict = {
        "Total Commits": 0,
        "Morning Commits": 0,
        "Afternoon Commits": 0,
        "MR Created": 0,
        "MR Merged": 0,
        "MR Open": 0,
        "MR Closed": 0,
        "MR Assigned": 0,
        "Issues Raised": 0,
        "Issues Closed": 0,
        "Issues Assigned": 0,
        "Team Score": 0,
        "Corpus Files": 0,
        "time_spent_seconds": 0,
        "mrs_open_time": 0,
        "mrs_merged_time": 0,
        "issues_open_time": 0,
        "issues_closed_time": 0,
    }
    for row in member_rows:
        for key in totals:
            if key == "Corpus Files":
                cf = row.get("corpus_files")
                if isinstance(cf, dict):
                    totals[key] += sum(len(v) for v in cf.values())
                continue

            src = "Score" if key == "Team Score" else key
            totals[key] += row.get(src, 0)

    # Add formatted team time spent for display
    totals["Time Spent"] = format_time_spent(totals["time_spent_seconds"])
    return totals


def _team_name_exists(name: str, exclude_index: int | None = None) -> bool:
    """Return True if a team with this name already exists (optionally skipping one index)."""
    for idx, t in enumerate(st.session_state["teams"]):
        if idx == exclude_index:
            continue
        if t["team_name"].strip().lower() == name.strip().lower():
            return True
    return False


def _validate_json_teams(data: dict) -> tuple[list[dict], str]:
    """Validate teams.json structure. Returns (teams_list, error_msg)."""
    if not isinstance(data, dict) or "teams" not in data:
        return [], "Invalid JSON: missing 'teams' key."

    teams = data["teams"]
    if not isinstance(teams, list) or not teams:
        return [], "Invalid JSON: 'teams' must be a non-empty list."

    validated = []
    seen_names = set()
    existing_names = {t["team_name"].strip().lower() for t in st.session_state.get("teams", [])}

    for idx, t in enumerate(teams):
        tname = t.get("team_name")
        pname = t.get("project_name")
        members = t.get("members")

        if not tname or not isinstance(tname, str):
            return [], f"Team #{idx + 1} is missing a valid 'team_name'."
        if pname is None or not isinstance(pname, str):
            return [], f"Team '{tname}' is missing a valid 'project_name'."
        if not members or not isinstance(members, list):
            return [], f"Team '{tname}' must have a non-empty 'members' list."

        lower_name = tname.strip().lower()
        if lower_name in seen_names:
            return [], f"Duplicate team name in JSON: '{tname}'."
        if lower_name in existing_names:
            return [], f"Team '{tname}' already exists in session."

        seen_names.add(lower_name)

        valid_members = []
        for midx, m in enumerate(members):
            muser = m.get("username")
            if not muser or not isinstance(muser, str):
                return [], f"Member #{midx + 1} in team '{tname}' is missing a valid 'username'."
            valid_members.append(
                {
                    "name": m.get("name", ""),
                    "username": muser,
                    "user_id": m.get("user_id"),
                    "global_username": m.get("global_username", ""),
                    "global_email": m.get("global_email", ""),
                    "date_of_joining": m.get("date_of_joining", ""),
                }
            )

        validated.append(
            {
                "team_name": tname.strip(),
                "project_name": (pname or "").strip(),
                "members": valid_members,
                "scope": t.get("scope", "all"),
            }
        )

    return validated, ""


def _build_excel_export(team_data: dict) -> bytes:
    """Multi-sheet Excel: Sheet 1 = ranking, Sheet N = per-team member details."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        lb_rows = [
            {"Team": tn, "Project": meta.get("project_name", ""), **totals}
            for tn, (meta, _, totals) in team_data.items()
        ]
        (
            pd.DataFrame(lb_rows)
            .sort_values("Team Score", ascending=False)
            .to_excel(writer, index=False, sheet_name="Batch Ranking")
        )
        for team_name, (_, member_rows, _) in team_data.items():
            if member_rows:
                # Exclude internal raw lists from individual sheets to keep them clean
                exclude_cols = {"mrs_list", "issues_list", "commits_list", "corpus_files", "time_spent_seconds"}
                df_team = pd.DataFrame(member_rows)
                display_cols = [c for c in df_team.columns if c not in exclude_cols]
                df_team[display_cols].to_excel(writer, index=False, sheet_name=team_name[:31])
            else:
                pd.DataFrame().to_excel(writer, index=False, sheet_name=team_name[:31])
    return output.getvalue()


def _build_individual_metrics_excel_export(team_data: dict) -> bytes:
    """Single-sheet Excel containing all members from all teams with attendance and consistency metrics."""
    output = io.BytesIO()
    all_member_data = []

    for team_name, (_, member_rows, _) in team_data.items():
        for row in member_rows:
            # Re-calculate metrics to ensure they are present even if not in cache
            mrs = row.get("mrs_list", [])
            issues = row.get("issues_list", [])
            commits = row.get("commits_list", [])
            cf = row.get("corpus_files") or {}
            activity_map = _get_daily_activity_counts(mrs, issues, commits, corpus_files=cf)

            joining_date_str = row.get("Date of Joining")
            joining_date = None
            if joining_date_str:
                try:
                    joining_date = dateutil.parser.parse(joining_date_str).date()
                except Exception:
                    pass

            active_days, total_days, consistency_pct, working_days, attendance_pct = _get_contribution_index(
                activity_map, row.get("Username"), joining_date=joining_date
            )

            total_corpus = sum(len(v) for v in cf.values()) if isinstance(cf, dict) else 0

            export_row = {
                "Team Name": team_name,
                "Name": row.get("Name", ""),
                "Username": row.get("Username", ""),
                "Date of Joining": row.get("Date of Joining", ""),
                "Status": row.get("Status", ""),
                "Total Commits": row.get("Total Commits", 0),
                "Morning Commits": row.get("Morning Commits", 0),
                "Afternoon Commits": row.get("Afternoon Commits", 0),
                "MR Created": row.get("MR Created", 0),
                "MR Merged": row.get("MR Merged", 0),
                "MR Open": row.get("MR Open", 0),
                "MR Closed": row.get("MR Closed", 0),
                "MR Assigned": row.get("MR Assigned", 0),
                "Issues Raised": row.get("Issues Raised", 0),
                "Issues Closed": row.get("Issues Closed", 0),
                "Issues Assigned": row.get("Issues Assigned", 0),
                "Score": row.get("Score", 0),
                "Corpus Files": total_corpus,
                "Active Days": active_days,
                "Consistency %": f"{consistency_pct:.1f}%",
                "Attendance %": f"{attendance_pct:.1f}%",
                "Time Spent (Format)": row.get("Time Spent", "0 min"),
                "Time Spent (Seconds)": row.get("time_spent_seconds", 0),
                "MRs Open Time (s)": row.get("mrs_open_time", 0),
                "MRs Merged Time (s)": row.get("mrs_merged_time", 0),
                "Issues Open Time (s)": row.get("issues_open_time", 0),
                "Issues Closed Time (s)": row.get("issues_closed_time", 0),
            }
            all_member_data.append(export_row)

    if all_member_data:
        df = pd.DataFrame(all_member_data)
        # Sort by Team and then by Score
        df = df.sort_values(by=["Team Name", "Score"], ascending=[True, False])
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Individual Metrics")

    return output.getvalue()


# ---------------------------------------------------------------------------
# UI: CSV Bulk Upload
# ---------------------------------------------------------------------------


# Removed _render_csv_upload


# ---------------------------------------------------------------------------
# UI: Create Team Form
# ---------------------------------------------------------------------------


def _render_create_team_form(scope: str = "all") -> None:
    pass


# ---------------------------------------------------------------------------
# UI: Edit Team Form
# ---------------------------------------------------------------------------


def _render_edit_form(edit_idx: int) -> None:
    """
    Render a pre-filled editable form for the team at `edit_idx`.
    Uses _lb_edit_draft in session state as the working copy.
    """
    team = st.session_state["teams"][edit_idx]

    # Initialise draft when first entering edit for this team
    draft = st.session_state["_lb_edit_draft"]
    if draft.get("_source_index") != edit_idx:
        st.session_state["_lb_edit_draft"] = copy.deepcopy(team)
        st.session_state["_lb_edit_draft"]["_source_index"] = edit_idx
        draft = st.session_state["_lb_edit_draft"]

    st.markdown(f"#### ✏️ Editing: **{team['team_name']}**")

    col_a, col_b = st.columns(2)
    with col_a:
        new_team_name = st.text_input("Team Name *", value=draft["team_name"], key="_lb_edit_team_name")
    with col_b:
        new_project_name = st.text_input(
            "Project Name", value=draft.get("project_name", ""), key="_lb_edit_project_name"
        )

    st.markdown("##### 👥 Current Members")

    members: list[dict] = draft.get("members", [])
    if not members:
        st.info("No members. Add one below.")
    else:
        for m_idx, member in enumerate(members):
            mc1, mc2, mc3, mc4, mc5 = st.columns([2, 2, 2, 2, 0.5])
            with mc1:
                members[m_idx]["name"] = st.text_input(
                    "Name", value=member.get("name", ""), key=f"_lb_edit_m_name_{m_idx}"
                )
            with mc2:
                members[m_idx]["username"] = st.text_input(
                    "GitLab Username *",
                    value=member.get("username", ""),
                    key=f"_lb_edit_m_user_{m_idx}",
                )
            with mc3:
                members[m_idx]["global_username"] = st.text_input(
                    "Global Username",
                    value=member.get("global_username", ""),
                    key=f"_lb_edit_m_global_{m_idx}",
                )
            with mc4:
                members[m_idx]["date_of_joining"] = st.text_input(
                    "DOJ",
                    value=member.get("date_of_joining", ""),
                    key=f"_lb_edit_m_doj_{m_idx}",
                )
            with mc5:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑", key=f"_lb_edit_rm_{m_idx}", help="Remove this member"):
                    st.session_state["_lb_edit_draft"]["members"].pop(m_idx)
                    st.rerun()

    st.markdown("##### ➕ Add New Member")
    nc1, nc2, nc3 = st.columns([2, 2, 1])
    with nc1:
        new_m_name = st.text_input("Member Name", key="_lb_edit_new_m_name", placeholder="Jane Doe")
    with nc2:
        new_m_user = st.text_input("GitLab Username *", key="_lb_edit_new_m_user", placeholder="jane_doe")
    with nc3:
        new_m_id = st.number_input("User ID (opt.)", key="_lb_edit_new_m_id", min_value=0, step=1, value=0)

    if st.button("➕ Add Member", key="_lb_edit_add_member"):
        if not new_m_user.strip():
            st.warning("GitLab Username is required.")
        elif new_m_user.strip().lower() in [
            m["username"].lower() for m in st.session_state["_lb_edit_draft"]["members"]
        ]:
            st.warning(f"**{new_m_user}** is already in the list.")
        else:
            st.session_state["_lb_edit_draft"]["members"].append(
                {
                    "name": new_m_name.strip(),
                    "username": new_m_user.strip(),
                    "user_id": int(new_m_id) if new_m_id else None,
                }
            )
            st.rerun()

    st.markdown("---")
    btn_col1, btn_col2, _ = st.columns([1, 1, 4])

    with btn_col1:
        if st.button("💾 Update Team", type="primary", key="_lb_edit_save"):
            # Sync text inputs back (Streamlit updates widget keys on rerun)
            draft["team_name"] = new_team_name
            draft["project_name"] = new_project_name

            # Validation
            if not (new_team_name or "").strip():
                st.error("Team Name cannot be empty.")
            elif not draft.get("members"):
                st.error("Team must have at least one member.")
            elif _team_name_exists(new_team_name or "", exclude_index=edit_idx):
                st.error(f'Another team named **"{new_team_name}"** already exists.')
            else:
                # Commit draft → actual team list
                clean = {
                    "team_name": (new_team_name or "").strip(),
                    "project_name": (new_project_name or "").strip(),
                    "members": [
                        {k: v for k, v in m.items() if k != "_source_index"}
                        for m in draft["members"]
                        if m.get("username", "").strip()
                    ],
                }
                st.session_state["teams"][edit_idx] = clean
                st.session_state["edit_team_index"] = None
                st.session_state["_lb_edit_draft"] = {}
                st.session_state["_lb_triggered"] = False  # require re-run after edit
                st.session_state["_lb_cached_results"] = None  # invalidate cache
                st.session_state["_lb_last_filters"] = None
                st.success(f'✅ Team **"{new_team_name}"** updated!')
                st.rerun()

    with btn_col2:
        if st.button("✖ Cancel", key="_lb_edit_cancel"):
            st.session_state["edit_team_index"] = None
            st.session_state["_lb_edit_draft"] = {}
            st.rerun()


# ---------------------------------------------------------------------------
# UI: Teams Overview & Management
# ---------------------------------------------------------------------------


def _render_teams_overview(filter_team_name: str | None = None) -> None:
    """Show all configured teams with Edit and Delete controls."""
    all_teams: list[dict] = st.session_state["teams"]

    if filter_team_name == "All Teams" or filter_team_name is None:
        # In "All Teams" context: only show teams with scope 'all' (or no scope set = legacy)
        teams = [t for t in all_teams if t.get("scope", "all") == "all"]
    elif filter_team_name == "No Team":
        teams = []
    else:
        # Specific team selected
        teams = [t for t in all_teams if t["team_name"] == filter_team_name]
    active_edit = st.session_state.get("edit_team_index")

    if not teams:
        st.info("No teams created yet. Use **➕ Create New Team** to get started.")
        return

    st.markdown(f"**{len(teams)} team(s) configured:**")

    for idx, team in enumerate(teams):
        members = team.get("members", [])
        project = team.get("project_name", "—") or "—"
        usernames = ", ".join(m["username"] for m in members) or "—"

        # If this team is being edited, render the edit form inline
        if active_edit == idx:
            _render_edit_form(idx)
            st.divider()
            continue

        col_info, col_edit, col_del = st.columns([6, 1, 1])
        with col_info:
            st.markdown(
                f"🏅 **{team['team_name']}** &nbsp;|&nbsp; "
                f"Project: _{project}_ &nbsp;|&nbsp; "
                f"Members ({len(members)}): `{usernames}`"
            )
        with col_edit:
            if st.button("✏️", key=f"_lb_edit_team_{idx}", help="Edit this team"):
                # Close create form if open
                st.session_state["_lb_show_create_form"] = False
                st.session_state["edit_team_index"] = idx
                st.session_state["_lb_edit_draft"] = {}  # reset so draft re-initialises
                st.rerun()
        with col_del:
            if st.button("🗑", key=f"_lb_del_team_{idx}", help="Delete this team"):
                st.session_state["teams"].pop(idx)
                if st.session_state.get("edit_team_index") == idx:
                    st.session_state["edit_team_index"] = None
                    st.session_state["_lb_edit_draft"] = {}
                st.session_state["_lb_triggered"] = False
                st.session_state["_lb_cached_results"] = None  # invalidate cache
                st.session_state["_lb_last_filters"] = None
                st.rerun()


# ---------------------------------------------------------------------------
# UI: Per-Team Result Section
# ---------------------------------------------------------------------------


def _render_team_result(
    team_name: str, project_name: str, member_rows: list[dict], totals: dict, key_prefix: str = ""
) -> None:
    """Render analytics for one team: metrics, member table, group breakdown."""
    st.subheader(f"🏅 {team_name}")
    if project_name:
        st.caption(f"Project: {project_name}")

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Team Score", totals["Team Score"])
    c2.metric("Total Commits", totals["Total Commits"])
    c3.metric("MR Merged", totals["MR Merged"])
    c4.metric("Issues Closed", totals["Issues Closed"])
    c5.metric("Total Files", totals.get("Corpus Files", 0))
    with c6:
        st.metric("Time Spent", totals.get("Time Spent", "0 min"))
        with st.popover("🕒 Breakdown"):
            st.write(f"**MRs Open:** {format_time_spent(totals.get('mrs_open_time', 0))}")
            st.write(f"**MRs Merged:** {format_time_spent(totals.get('mrs_merged_time', 0))}")
            st.write(f"**Issues Open:** {format_time_spent(totals.get('issues_open_time', 0))}")
            st.write(f"**Issues Closed:** {format_time_spent(totals.get('issues_closed_time', 0))}")
    c7.metric("Members", len(member_rows))

    display_cols = [
        "Username",
        "Status",
        "Total Commits",
        "Morning Commits",
        "Afternoon Commits",
        "MR Created",
        "MR Merged",
        "MR Open",
        "MR Closed",
        "MR Assigned",
        "Issues Raised",
        "Issues Closed",
        "Issues Assigned",
        "Groups",
        "Score",
        "Corpus Files",
        "Time Spent",
    ]
    df = pd.DataFrame(member_rows)
    # Compute a friendly Corpus Files total count column if the raw data exists
    if "corpus_files" in df.columns:
        df["Corpus Files"] = df["corpus_files"].apply(
            lambda m: sum(len(v) for v in m.values()) if isinstance(m, dict) else 0
        )
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], width="stretch", hide_index=True)

    group_rows = [
        {"Username": r["Username"], "Groups": r.get("Groups", 0)} for r in member_rows if r.get("Status") == "Success"
    ]
    if group_rows:
        with st.expander("👥 Group Breakdown"):
            st.dataframe(pd.DataFrame(group_rows), width="stretch", hide_index=True)

    _render_detailed_contributions(member_rows, key_prefix=key_prefix or team_name)

    st.divider()


def _get_daily_activity_counts(mrs, issues, commits, corpus_files: dict | None = None) -> dict[str, int]:
    """Aggregates all contributions into a date-based activity map {YYYY-MM-DD: count}.

    GitLab timestamps (MRs / issues / commits) are already converted by the API.
    Corpus timestamps are stored in UTC and converted to IST (UTC+5:30) before
    extracting the calendar date.
    """
    IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
    activity_map: dict[str, int] = {}

    def add_to_map(date_str):
        if not date_str:
            return
        day = None
        if isinstance(date_str, str):
            if "T" in date_str:
                day = date_str.split("T")[0]
            elif "-" in date_str and len(date_str.split("-")) >= 3:
                day = date_str.split("-")[0:3] if len(date_str) > 10 else date_str
            else:
                try:
                    day = datetime.date.fromisoformat(date_str).isoformat()
                except Exception:
                    return
        elif hasattr(date_str, "isoformat"):
            day = date_str.date().isoformat() if hasattr(date_str, "date") else date_str.isoformat()

        if day and isinstance(day, str) and len(day) == 10:
            activity_map[day] = activity_map.get(day, 0) + 1

    def add_corpus_to_map(created_at: str) -> None:
        """Convert UTC ISO timestamp to IST date and add to the activity map."""
        if not created_at:
            return
        try:
            # Parse as UTC (strip trailing Z, add explicit UTC offset)
            ts_str = created_at.rstrip("Z")
            if "+" not in ts_str and ts_str.count("-") < 3:
                # No timezone info — assume UTC
                dt_utc = datetime.datetime.fromisoformat(ts_str).replace(tzinfo=datetime.timezone.utc)
            else:
                dt_utc = datetime.datetime.fromisoformat(created_at)
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
            dt_ist = dt_utc + IST_OFFSET
            day = dt_ist.date().isoformat()
            activity_map[day] = activity_map.get(day, 0) + 1
        except Exception:
            # Fallback: naive date split
            day = created_at[:10] if len(created_at) >= 10 else ""
            if day and len(day) == 10:
                activity_map[day] = activity_map.get(day, 0) + 1

    for m in mrs:
        add_to_map(m.get("created_at"))
    for i in issues:
        add_to_map(i.get("created_at"))
    for c in commits:
        add_to_map(c.get("date"))

    # Corpus contributions — convert UTC → IST before date extraction
    if corpus_files:
        for bucket_items in corpus_files.values():
            for entry in bucket_items:
                add_corpus_to_map(entry.get("created_at", ""))

    return activity_map


def _build_contributions_by_day(
    mrs: list,
    issues: list,
    commits: list,
    corpus_files: dict | None = None,
) -> dict[str, dict[str, list]]:
    """Group every contribution by its IST calendar date.

    Returns:
        {"YYYY-MM-DD": {"mrs": [...], "issues": [...], "commits": [...], "corpus": [...]}}
    """
    IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

    def _date_from_utc(ts: str) -> str:
        """Parse a UTC ISO timestamp and return the IST date string (YYYY-MM-DD)."""
        if not ts:
            return ""
        try:
            ts_str = ts.rstrip("Z")
            if "+" not in ts_str and ts_str.count("-") < 3:
                dt = datetime.datetime.fromisoformat(ts_str).replace(tzinfo=datetime.timezone.utc)
            else:
                dt = datetime.datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
            return (dt + IST_OFFSET).date().isoformat()
        except Exception:
            return ts[:10] if len(ts) >= 10 else ""

    by_day: dict[str, dict[str, list]] = {}

    def _ensure(d: str) -> None:
        if d and d not in by_day:
            by_day[d] = {"mrs": [], "issues": [], "commits": [], "corpus": []}

    for m in mrs:
        d = _date_from_utc(m.get("created_at", ""))
        _ensure(d)
        if d:
            by_day[d]["mrs"].append(m)

    for i in issues:
        d = _date_from_utc(i.get("created_at", ""))
        _ensure(d)
        if d:
            by_day[d]["issues"].append(i)

    for c in commits:
        # Commits store date as YYYY-MM-DD already (IST via GitLab API)
        d = c.get("date", "")
        if d and len(d) >= 10:
            d = d[:10]
        _ensure(d)
        if d:
            by_day[d]["commits"].append(c)

    if corpus_files:
        for bucket_items in corpus_files.values():
            for entry in bucket_items:
                d = _date_from_utc(entry.get("created_at", ""))
                _ensure(d)
                if d:
                    by_day[d]["corpus"].append(entry)

    return by_day


def _get_group_start_date(username: str | None) -> datetime.date | None:
    """Return cohort start date for known usernames; otherwise None.
    Note: Cohort start dates are currently not supported without BATCH_CONFIG.
    """
    return None


def _get_contribution_index(
    activity_map: dict[str, int], username: str | None = None, joining_date: datetime.date | None = None
) -> tuple[int, int, float, int, float]:
    """
    Returns (active_days, total_days, consistency_pct, working_days, attendance_pct)
    for the current leaderboard context.
    """
    active_days = sum(1 for count in activity_map.values() if count > 0)
    today = datetime.date.today()

    # Calculate Total Days (Priority: Joining Date -> Date Filter -> Activity Span)
    total_days = 0
    from_date = st.session_state.get("_lb_from_date")
    to_date = st.session_state.get("_lb_to_date")

    if joining_date:
        total_days = max((today - joining_date).days + 1, 0)
    else:
        cohort_start = _get_group_start_date(username)
        if cohort_start:
            total_days = max((today - cohort_start).days + 1, 0)
        elif from_date and to_date:
            total_days = (to_date - from_date).days + 1
        elif activity_map:
            try:
                days = sorted(activity_map.keys())
                start = datetime.date.fromisoformat(days[0])
                end = datetime.date.fromisoformat(days[-1])
                total_days = (end - start).days + 1
            except Exception:
                total_days = active_days

    consistency_pct = (active_days / total_days * 100.0) if total_days > 0 else 0.0

    # Calculate Attendance based on Date of Joining
    working_days = 0
    if joining_date:
        curr = joining_date
        while curr <= today:
            # Exclude every Monday (curr.weekday() == 0)
            is_monday = curr.weekday() == 0
            # Exclude every month's first Sunday (curr.weekday() == 6 and day 1-7)
            is_first_sunday = curr.weekday() == 6 and curr.day <= 7

            if not is_monday and not is_first_sunday:
                working_days += 1
            curr += datetime.timedelta(days=1)

    attendance_pct = (active_days / working_days * 100.0) if working_days > 0 else 0.0

    return active_days, total_days, consistency_pct, working_days, attendance_pct


def _render_activity_heatmap(
    activity_map: dict[str, int],
    contributions_by_day: dict[str, dict[str, list]] | None = None,
    username: str = "user",
) -> None:
    """Renders a GitLab-style activity heatmap (364 days).

    When *contributions_by_day* is provided, every active day cell becomes a
    clickable box that toggles a popover listing all GitLab and Corpus
    contributions for that day. Uses a pure-CSS checkbox hack for reliability.
    """
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=363)
    while start_date.weekday() != 0:
        start_date -= datetime.timedelta(days=1)

    heatmap_styles = """
    <style>
        .heatmap-wrapper {
            background: rgba(13, 14, 18, 0.95);
            border: 1px solid rgba(120, 129, 149, 0.15);
            border-radius: 6px;
            padding: 16px 12px;
            margin: 10px 0;
            overflow-x: auto;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .heatmap-months {
            display: flex;
            margin-left: 38px;
            margin-bottom: 6px;
            height: 18px;
        }
        .heatmap-month-label {
            flex: 1;
            font-size: 11px;
            color: #8b949e;
            min-width: 0;
        }
        .heatmap-weeks {
            display: flex;
            gap: 4px;
        }
        .heatmap-day-labels {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 115px;
            padding-right: 8px;
            font-size: 10px;
            color: #8b949e;
        }
        .heatmap-week {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        /* ── base cell ── */
        .heatmap-day {
            width: 13px;
            height: 13px;
            border-radius: 2px;
            background: rgba(255, 255, 255, 0.08);
            outline: 1px solid rgba(255,255,255,0.02);
            cursor: pointer;
            display: block;
        }
        .heatmap-day:hover {
            transform: scale(1.4);
            z-index: 5;
            box-shadow: 0 0 8px rgba(52, 152, 219, 0.6);
        }
        /* ── levels ── */
        .heatmap-day-0 { background: rgba(255,255,255,0.08); }
        .heatmap-day-1 { background: #1e3a5f; }
        .heatmap-day-2 { background: #2b5a91; }
        .heatmap-day-3 { background: #3b7bc4; }
        .heatmap-day-4 { background: #4b9cf7; }
        .heatmap-day-5 { background: #70b1ff; }
        .heatmap-today {
            outline: 2px solid #70b1ff !important;
            outline-offset: -1px;
        }
        /* ── popover checkbox hack ── */
        .hp-cb {
            display: none !important;
        }
        .hp-day-wrapper {
            position: relative;
            display: inline-block;
            line-height: 0;
        }
        .heatmap-popover {
            display: none;
            position: absolute;
            top: calc(100% + 8px);
            left: 50%;
            transform: translateX(-50%);
            min-width: 280px;
            max-width: 380px;
            background: #1a1d2e;
            border: 1px solid rgba(120, 129, 149, 0.35);
            border-radius: 10px;
            padding: 12px 14px;
            z-index: 1000;
            box-shadow: 0 12px 40px rgba(0,0,0,0.6);
            max-height: 350px;
            overflow-y: auto;
            font-size: 0.78rem;
            color: #d9e1ee;
            line-height: 1.4;
        }
        .hp-cb:checked ~ .heatmap-popover {
            display: block;
        }
        .heatmap-popover::before {
            content: '';
            position: absolute;
            top: -5px;
            left: 50%;
            transform: translateX(-50%) rotate(45deg);
            width: 10px;
            height: 10px;
            background: #1a1d2e;
            border-top: 1px solid rgba(120,129,149,0.35);
            border-left: 1px solid rgba(120,129,149,0.35);
        }
        .hp-date {
            font-weight: 700;
            font-size: 0.82rem;
            color: #70b1ff;
            margin-bottom: 6px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            padding-bottom: 4px;
            padding-right: 25px; /* space for X */
        }
        .hp-section {
            margin: 8px 0 4px 0;
            font-weight: 600;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            opacity: 0.7;
            border-bottom: 1px dashed rgba(255,255,255,0.05);
        }
        .hp-item {
            display: flex;
            align-items: flex-start;
            gap: 5px;
            padding: 3px 0;
            font-size: 0.78rem;
            line-height: 1.35;
        }
        .hp-link {
            color: #d9e1ee;
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 280px;
            display: inline-block;
        }
        .hp-link:hover { color: #70b1ff; text-decoration: underline; }
        .hp-badge {
            display: inline-block;
            padding: 1px 5px;
            border-radius: 4px;
            font-size: 0.62rem;
            font-weight: 700;
            text-transform: uppercase;
            flex-shrink: 0;
            margin-top: 1px;
        }
        .hp-mr    { background: rgba(255,165,0,0.2);  color: #ffa500; }
        .hp-issue { background: rgba(255,215,0,0.15); color: #ffd700; }
        .hp-commit{ background: rgba(52,152,219,0.2); color: #3498db; }
        .hp-audio { background: rgba(237,137,54,0.2); color: #ed8936; }
        .hp-image { background: rgba(56,178,172,0.2); color: #38b2ac; }
        .hp-video { background: rgba(229,62,62,0.2);  color: #e53e3e; }
        .hp-file  { background: rgba(159,122,234,0.2); color: #9f7aea; }
        .hp-close {
            position: absolute;
            top: 10px;
            right: 12px;
            font-size: 24px;
            font-weight: 300;
            color: #8b949e;
            cursor: pointer;
            line-height: 1;
            transition: color 0.2s, transform 0.2s;
            z-index: 1001;
            user-select: none;
        }
        .hp-close:hover {
            color: #ff4d4d;
            transform: scale(1.1);
        }
        /* ── legend ── */
        .heatmap-legend {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 5px;
            margin-top: 12px;
            font-size: 11px;
            color: #8b949e;
        }
        .heatmap-legend-box {
            width: 13px;
            height: 13px;
            border-radius: 2px;
        }
    </style>
    """

    weeks_data: list[list[dict[str, Any]]] = []
    current_date = start_date
    month_starts = []
    last_month = None

    for w in range(53):
        week_days = []
        for _d in range(7):
            date_val = current_date.isoformat()
            count_val: int = activity_map.get(date_val, 0)
            is_today = current_date == today
            week_days.append(
                {
                    "date": date_val,
                    "count": count_val,
                    "is_today": is_today,
                    "day": current_date.day,
                    "month": current_date.month,
                }
            )
            current_date += datetime.timedelta(days=1)
        weeks_data.append(week_days)

        if last_month != current_date.month:
            month_starts.append((w, current_date.strftime("%b")))
            last_month = current_date.month

    month_labels_html = []
    for w in range(53):
        label = ""
        for mw, mname in month_starts:
            if mw == w:
                label = f'<div class="heatmap-month-label">{mname}</div>'
                break
        month_labels_html.append(label)

    weeks_html = []
    from html import escape

    for week_days in weeks_data:
        days_html = []
        for day_info in week_days:
            count: int = day_info["count"]  # type: ignore[assignment]
            date_str = day_info["date"]
            if count == 0:
                level = "heatmap-day-0"
            elif count <= 2:
                level = "heatmap-day-1"
            elif count <= 5:
                level = "heatmap-day-2"
            elif count <= 10:
                level = "heatmap-day-3"
            elif count <= 20:
                level = "heatmap-day-4"
            else:
                level = "heatmap-day-5"

            today_class = "heatmap-today" if day_info["is_today"] else ""
            title = f"{date_str}: {count} contribution{'s' if count != 1 else ''}"

            date_str = str(day_info["date"])
            day_contribs = None
            if isinstance(contributions_by_day, dict):
                day_contribs = contributions_by_day.get(date_str)
            if count > 0 and day_contribs:
                # Use a unique ID for the checkbox hack
                # Slugify username to ensure valid HTML ID
                user_slug = "".join(c if c.isalnum() else "_" for c in username)
                cb_id = f"hp_cb_{user_slug}_{date_str}"

                CORPUS_ICONS = {"audio": "🎤", "image": "🖼️", "video": "🎬", "file": "📎"}
                CORPUS_BADGE = {"audio": "hp-audio", "image": "hp-image", "video": "hp-video", "file": "hp-file"}

                popover_inner = f'<label for="{cb_id}" class="hp-close">&times;</label>'
                popover_inner += f'<div class="hp-date">📅 {date_str}</div>'

                day_mrs = day_contribs.get("mrs", [])
                if day_mrs:
                    popover_inner += '<div class="hp-section">📙 Merge Requests</div>'
                    for m in day_mrs:
                        t = escape(m.get("title", "MR"))[:60]
                        u = m.get("web_url", "#")
                        state = m.get("state", "")
                        popover_inner += (
                            f'<div class="hp-item">'
                            f'<span class="hp-badge hp-mr">{state}</span>'
                            f'<a href="{u}" target="_blank" class="hp-link" title="{t}">{t}</a>'
                            f"</div>"
                        )
                day_issues = day_contribs.get("issues", [])
                if day_issues:
                    popover_inner += '<div class="hp-section">🎫 Issues</div>'
                    for i in day_issues:
                        t = escape(i.get("title", "Issue"))[:60]
                        u = i.get("web_url", "#")
                        state = i.get("state", "")
                        popover_inner += (
                            f'<div class="hp-item">'
                            f'<span class="hp-badge hp-issue">{state}</span>'
                            f'<a href="{u}" target="_blank" class="hp-link" title="{t}">{t}</a>'
                            f"</div>"
                        )
                day_commits = day_contribs.get("commits", [])
                if day_commits:
                    popover_inner += '<div class="hp-section">💻 Commits</div>'
                    for c in day_commits:
                        msg = escape(c.get("message", "commit").split("\n")[0])[:60]
                        sha = c.get("short_id", "")
                        u = c.get("web_url", "#")
                        popover_inner += (
                            f'<div class="hp-item">'
                            f'<span class="hp-badge hp-commit">{sha}</span>'
                            f'<a href="{u}" target="_blank" class="hp-link" title="{msg}">{msg}</a>'
                            f"</div>"
                        )
                day_corpus = day_contribs.get("corpus", [])
                if day_corpus:
                    popover_inner += '<div class="hp-section">📁 Corpus</div>'
                    for entry in day_corpus:
                        mtype = entry.get("media_type", "file")
                        icon = CORPUS_ICONS.get(mtype, "📎")
                        badge_cls = CORPUS_BADGE.get(mtype, "hp-file")
                        fname = escape(entry.get("filename", "file"))[:50]
                        u = entry.get("url", "#")
                        popover_inner += (
                            f'<div class="hp-item">'
                            f'<span class="hp-badge {badge_cls}">{icon} {mtype}</span>'
                            f'<a href="{u}" target="_blank" class="hp-link" title="{fname}">{fname}</a>'
                            f"</div>"
                        )

                days_html.append(
                    f'<div class="hp-day-wrapper">'
                    f'<input type="checkbox" id="{cb_id}" class="hp-cb">'
                    f'<label for="{cb_id}" class="heatmap-day {level} {today_class}" title="{title}"></label>'
                    f'<div class="heatmap-popover">{popover_inner}</div>'
                    f"</div>"
                )
            else:
                days_html.append(f'<div class="heatmap-day {level} {today_class}" title="{title}"></div>')
        weeks_html.append(f'<div class="heatmap-week">{"".join(days_html)}</div>')

    legend_html = """
    <div class="heatmap-legend">
        <span>Less</span>
        <div class="heatmap-legend-box" style="background: rgba(255,255,255,0.08);"></div>
        <div class="heatmap-legend-box" style="background: #1e3a5f;"></div>
        <div class="heatmap-legend-box" style="background: #2b5a91;"></div>
        <div class="heatmap-legend-box" style="background: #3b7bc4;"></div>
        <div class="heatmap-legend-box" style="background: #4b9cf7;"></div>
        <div class="heatmap-legend-box" style="background: #70b1ff;"></div>
        <span>More</span>
    </div>
    """

    full_heatmap_html = f"""
    {heatmap_styles}
    <div class="heatmap-wrapper">
        <div class="heatmap-months">
            {"".join(month_labels_html)}
        </div>
        <div class="heatmap-weeks">
            <div class="heatmap-day-labels">
                <span></span>
                <span>Mon</span>
                <span></span>
                <span>Wed</span>
                <span></span>
                <span>Fri</span>
                <span></span>
            </div>
            {"".join(weeks_html)}
        </div>
        {legend_html}
    </div>
    """
    st.markdown(full_heatmap_html, unsafe_allow_html=True)


def _render_detailed_contributions(member_rows: list[dict], key_prefix: str = "") -> None:
    """Styled expander for detailed contributions (MR titles, Issue titles, Commit messages)."""
    with st.expander("🔍 Detailed Contributions"):
        valid_members = [r for r in member_rows if r.get("Status") == "Success"]
        if not valid_members:
            st.info("No successful member data to show contributions for.")
            return

        # Inject custom CSS for buttons to match the premium theme
        st.markdown(
            """
        <style>
            .stButton > button {
                border-radius: 8px !important;
                border: 1px solid rgba(120, 129, 149, 0.3) !important;
                background-color: rgba(28, 33, 46, 0.6) !important;
                color: #d9e1ee !important;
                font-size: 0.9em !important;
                font-weight: 500 !important;
                transition: all 0.2s ease !important;
            }
            .stButton > button:hover {
                border-color: #3498db !important;
                background-color: rgba(52, 152, 219, 0.1) !important;
                box-shadow: 0 0 10px rgba(52, 152, 219, 0.2) !important;
            }
        </style>
        """,
            unsafe_allow_html=True,
        )

        import plotly.express as px

        color_palette = (
            px.colors.qualitative.Pastel
            + px.colors.qualitative.Pastel1
            + px.colors.qualitative.Pastel2
            + px.colors.qualitative.Set3
        )
        color_map = {}
        for i, r in enumerate(sorted(valid_members, key=lambda x: x.get("Username", ""))):
            color_map[r.get("Username", "unknown")] = color_palette[i % len(color_palette)]

        pie_data = []
        for r in valid_members:
            # Issues Open can be approximated as Raised - Closed
            issues_open = max(0, r.get("Issues Raised", 0) - r.get("Issues Closed", 0))
            pie_data.append(
                {
                    "Username": r.get("Username", "unknown"),
                    "Commits": r.get("Total Commits", 0),
                    "Assigned MRs": r.get("MR Created", 0),
                    "Assigned Issues": r.get("Issues Raised", 0),
                    "Merged MRs": r.get("MR Merged", 0),
                    "Closed Issues": r.get("Issues Closed", 0),
                    "Open Issues": issues_open,
                    "Open MRs": r.get("MR Open", 0),
                }
            )

        if pie_data:
            st.markdown("### 📊 Group Contributions")
            df_pie = pd.DataFrame(pie_data)

            row1_charts = [
                ("Commits", "Commits"),
                ("Assigned MRs", "Assigned MRs"),
                ("Assigned Issues", "Assigned Issues"),
            ]
            row2_charts = [
                ("Merged MRs", "Merged MRs"),
                ("Closed Issues", "Closed Issues"),
                ("Open Issues", "Open Issues"),
                ("Open MRs", "Open MRs"),
            ]

            def render_row(chunk, cols):
                for col, (col_key, title) in zip(cols, chunk, strict=True):
                    with col:
                        if df_pie[col_key].sum() > 0:
                            fig = px.pie(
                                df_pie,
                                values=col_key,
                                names="Username",
                                title=title,
                                color="Username",
                                color_discrete_map=color_map,
                                height=220,
                            )
                            fig.update_layout(
                                showlegend=False,
                                margin={"t": 30, "b": 10, "l": 10, "r": 10},
                                title_font={"size": 13},
                                title_x=0.5,
                            )
                            fig.update_traces(textposition="inside", textinfo="percent+label")
                            chart_key = f"{key_prefix}_{col_key}" if key_prefix else col_key
                            st.plotly_chart(fig, width="stretch", key=chart_key)
                        else:
                            st.markdown(
                                f"<div style='text-align:center; padding:15px; border:1px dashed #555; border-radius:10px; margin-top:5px;'><h6 style='color:#ccc;margin:0;font-size:12px;'>{title}</h6><span style='color:#888;font-size:11px;'>No Data</span></div>",
                                unsafe_allow_html=True,
                            )

            # Row 1: 3 charts
            render_row(row1_charts, st.columns(3))

            st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

            # Row 2: 4 charts
            render_row(row2_charts, st.columns(4))

            st.divider()

        for row in valid_members:
            username = row.get("Username", "unknown")
            mrs = sorted(row.get("mrs_list", []), key=lambda x: str(x.get("created_at", "")), reverse=True)
            issues = sorted(row.get("issues_list", []), key=lambda x: str(x.get("created_at", "")), reverse=True)
            commits = sorted(
                row.get("commits_list", []), key=lambda x: f"{x.get('date', '')} {x.get('time', '')}", reverse=True
            )

            st.markdown(f"### 👤 {username}")

            corpus_files: dict = row.get("corpus_files") or {}
            total_corpus = sum(len(v) for v in corpus_files.values()) if corpus_files else 0

            # Render Activity Heatmap — includes corpus contributions (UTC→IST)
            # Build per-day breakdown so each cell can show a popover
            contributions_by_day = _build_contributions_by_day(mrs, issues, commits, corpus_files)
            activity_map = _get_daily_activity_counts(mrs, issues, commits, corpus_files=corpus_files)
            _render_activity_heatmap(activity_map, contributions_by_day=contributions_by_day, username=username)

            # Contribution Index
            joining_date_str = row.get("Date of Joining")
            joining_date = None
            if joining_date_str:
                try:
                    joining_date = dateutil.parser.parse(joining_date_str).date()
                except Exception:
                    pass

            active_days, total_days, consistency_pct, working_days, attendance_pct = _get_contribution_index(
                activity_map, username, joining_date=joining_date
            )
            total_contributions = len(mrs) + len(issues) + len(commits) + total_corpus
            collaboration_events = len(mrs) + len(issues)
            collaboration_pct = (collaboration_events / total_contributions) * 100 if total_contributions > 0 else 0.0
            # Header with info popover
            ci_head_a, ci_head_b = st.columns([0.9, 0.1])
            with ci_head_a:
                st.markdown("#### 📈 Contribution Index")
            with ci_head_b:
                with st.popover("ℹ️", help="How are these metrics calculated?"):
                    st.markdown("""
                    ### 📊 Metric Definitions

                    *   **Active Days**: Count of unique calendar days (IST) where you had at least one GitLab action or Corpus upload.
                    *   **Total Days**: The total number of calendar days from your Joining Date until today.
                    *   **Consistency %**: (Active Days / Total Days) × 100. Measures how regularly you contribute.
                    *   **Collaboration %**: (MRs + Issues) / (Total Contributions) × 100. Measures focus on team-sync tasks.
                    *   **Attendance**: (Active Days / Expected Working Days) × 100.
                        *   *Working Days* are calculated from your Joining Date until today.
                        *   **Exclusions**: All **Mondays** and the **1st Sunday** of every month are excluded.
                    """)

            idx_c1, idx_c2, idx_c3, idx_c4, idx_c5, idx_c6 = st.columns(6)
            idx_c1.metric("Active Days", active_days)
            idx_c2.metric("Total Days", total_days)
            idx_c3.metric("Consistency %", f"{consistency_pct:.1f}%")
            idx_c4.metric("Collaboration %", f"{collaboration_pct:.1f}%")

            time_spent_str = row.get("Time Spent", "0 min")
            idx_c5.metric("Time Spent", time_spent_str)
            idx_c5.caption("All-time (DOJ to Today)")
            with idx_c5:
                with st.popover("🕒 Details"):
                    st.write(f"**MRs Open:** {format_time_spent(row.get('mrs_open_time', 0))}")
                    st.write(f"**MRs Merged:** {format_time_spent(row.get('mrs_merged_time', 0))}")
                    st.write(f"**Issues Open:** {format_time_spent(row.get('issues_open_time', 0))}")
                    st.write(f"**Issues Closed:** {format_time_spent(row.get('issues_closed_time', 0))}")

                    item_breakdown = row.get("item_time_breakdown", [])
                    if item_breakdown:
                        st.divider()
                        st.markdown("#### 🕒 Per-Item Breakdown")

                        # Define categories
                        categories = [
                            ("MRs Open", "mr", "opened"),
                            ("MRs Merged", "mr", "merged"),
                            ("MRs Closed", "mr", "closed"),
                            ("Issues Open", "issue", "opened"),
                            ("Issues Closed", "issue", "closed"),
                        ]

                        for label, item_type, state in categories:
                            cat_items = [
                                i for i in item_breakdown if i.get("type") == item_type and i.get("state") == state
                            ]
                            if cat_items:
                                st.markdown(f"**{label}**")
                                # Sort by time spent (seconds) descending
                                sorted_items = sorted(cat_items, key=lambda x: x.get("seconds", 0), reverse=True)
                                for item in sorted_items:
                                    col_a, col_b = st.columns([0.3, 0.7])
                                    with col_a:
                                        st.markdown(f"[**{item['id']}**]({item.get('url', '#')})")
                                    with col_b:
                                        st.write(f"{format_time_spent(item['seconds'])}")
                                    st.caption(f"{item['title']}")
                                st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)

            if joining_date:
                idx_c6.metric("Attendance", f"{attendance_pct:.1f}%")
                idx_c6.caption(f"**{active_days} / {working_days}** working days")
            else:
                idx_c6.metric("Attendance", "N/A")
                idx_c6.caption("Set Joining Date in Roster")

            # Helper to generate list HTML
            def get_list_html(items, type_):
                def format_gitlab_date(iso_str):
                    if not iso_str:
                        return None
                    try:
                        dt = dateutil.parser.isoparse(iso_str)
                        return dt.strftime("%b %d, %I:%M %p")
                    except Exception:
                        return None

                html_lines = []
                for item in items:
                    url = item.get("web_url", "#")
                    created = format_gitlab_date(item.get("created_at"))

                    if type_ == "mr":
                        title = escape(item.get("title", "No Title"))
                        state = item.get("state", "unknown")
                        merged = format_gitlab_date(item.get("merged_at"))
                        closed = format_gitlab_date(item.get("closed_at"))

                        if state == "merged":
                            color = "#2ecc71"
                            status_info = f"Merged: {merged}" if merged else ""
                        elif state == "opened":
                            color = "#3498db"
                            status_info = ""
                        else:
                            color = "#e74c3c"
                            status_info = f"Closed: {closed}" if closed else ""

                        time_meta = f"Created: {created}" if created else ""
                        if status_info:
                            time_meta += f" | {status_info}" if time_meta else status_info

                        html_lines.append(
                            f"<li><a href='{url}' target='_blank' class='li-link'>{title} <span style='color:{color}; font-size:0.85em;'>( {state} )</span></a>"
                            f"<br><span style='color:#888; font-size:0.8em;'>{time_meta}</span></li>"
                        )
                    elif type_ == "issue":
                        title = escape(item.get("title", "No Title"))
                        state = item.get("state", "unknown")
                        closed = format_gitlab_date(item.get("closed_at"))

                        color = "#2ecc71" if state == "opened" else "#95a5a6"
                        status_info = f"Closed: {closed}" if (state == "closed" and closed) else ""

                        time_meta = f"Created: {created}" if created else ""
                        if status_info:
                            time_meta += f" | {status_info}" if time_meta else status_info

                        html_lines.append(
                            f"<li><a href='{url}' target='_blank' class='li-link'>{title} <span style='color:{color}; font-size:0.85em;'>( {state} )</span></a>"
                            f"<br><span style='color:#888; font-size:0.8em;'>{time_meta}</span></li>"
                        )
                    elif type_ == "commit":
                        msg = escape(item.get("message", "No Message")).split("\n")[0]
                        sha = item.get("short_id", "---")
                        date_str = item.get("date", "")
                        time_str = item.get("time", "")
                        time_meta = f"{date_str} {time_str}".strip()

                        html_lines.append(
                            f"<li><a href='{url}' target='_blank' class='li-link'><span style='color:#3498db; font-family:monospace;'>{sha}</span> {msg}</a>"
                            f"<br><span style='color:#888; font-size:0.8em;'>{time_meta}</span></li>"
                        )

                if not html_lines:
                    return "<p style='color:#888; font-style:italic;'>No items found.</p>"

                return f"""
                <style>
                    .li-link {{
                        color: inherit !important;
                        text-decoration: none !important;
                        transition: all 0.2s ease;
                    }}
                    .li-link:hover {{
                        text-decoration: underline !important;
                        opacity: 0.8;
                    }}
                </style>
                <ul style='list-style-type: disc; padding-left: 18px; color: #d9e1ee; font-size: 0.92em; line-height:1.5;'>
                    {"".join(html_lines)}
                </ul>
                """

            c1, c2, c3 = st.columns(3)

            # MRs Column
            with c1:
                st.markdown(
                    f"""
                <div style="background: rgba(255,165,0,0.06); border: 1px solid rgba(255,165,0,0.25); border-radius: 12px; padding: 15px; height: 350px; overflow-y: auto;">
                    <h4 style="margin-top:0; color:#ffa500; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(255,165,0,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>📙</span> MRs ({len(mrs)})
                    </h4>
                    {get_list_html(mrs, "mr")}
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Issues Column
            with c2:
                st.markdown(
                    f"""
                <div style="background: rgba(255,215,0,0.06); border: 1px solid rgba(255,215,0,0.25); border-radius: 12px; padding: 15px; height: 350px; overflow-y: auto;">
                    <h4 style="margin-top:0; color:#ffd700; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(255,215,0,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>🎫</span> Issues ({len(issues)})
                    </h4>
                    {get_list_html(issues, "issue")}
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # Commits Column
            with c3:
                st.markdown(
                    f"""
                <div style="background: rgba(52,152,219,0.06); border: 1px solid rgba(52,152,219,0.25); border-radius: 12px; padding: 15px; height: 350px; overflow-y: auto;">
                    <h4 style="margin-top:0; color:#3498db; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(52,152,219,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>💻</span> Commits ({len(commits)})
                    </h4>
                    {get_list_html(commits, "commit")}
                </div>
                """,
                    unsafe_allow_html=True,
                )

            # ── Corpus Media Section ─────────────────────────────────────────
            # Same scrollable-card style as MRs / Issues / Commits — links only, no inline players.
            def get_corpus_list_html(items: list, bucket: str, font_color: str) -> str:
                BUCKET_ICONS = {"audio": "🎤", "image": "🖼️", "video": "🎬", "file": "📎"}
                b_icon = BUCKET_ICONS.get(bucket, "📁")
                html_lines = []
                for entry in sorted(items, key=lambda x: x.get("created_at", ""), reverse=True):
                    fname = escape(entry.get("filename") or "file")
                    url = entry.get("url", "#")
                    ts_raw = entry.get("created_at", "")
                    ts = ts_raw[:16].replace("T", " ") if ts_raw else ""
                    time_meta = f"⏱ {ts}" if ts else ""
                    html_lines.append(
                        f"<li><a href='{url}' target='_blank' class='li-link'>"
                        f"<span style='color:{font_color}; margin-right:4px;'>{b_icon}</span>"
                        f"{fname}</a>"
                        + (f"<br><span style='color:#888; font-size:0.8em;'>{time_meta}</span>" if time_meta else "")
                        + "</li>"
                    )
                if not html_lines:
                    return "<p style='color:#888; font-style:italic;'>No items found.</p>"
                return (
                    "<ul style='list-style-type: disc; padding-left: 18px;"
                    " color: #d9e1ee; font-size: 0.92em; line-height:1.5;'>" + "".join(html_lines) + "</ul>"
                )

            corpus_cfg = [
                ("audio", "🎤", "#ed8936", "rgba(237,137,54,0.08)", "rgba(237,137,54,0.25)"),
                ("image", "🖼️", "#38b2ac", "rgba(56,178,172,0.08)", "rgba(56,178,172,0.25)"),
                ("video", "🎬", "#e53e3e", "rgba(229,62,62,0.08)", "rgba(229,62,62,0.25)"),
                ("file", "📄", "#9f7aea", "rgba(159,122,234,0.08)", "rgba(159,122,234,0.25)"),
            ]
            non_empty_corpus = [
                (k, icon, fc, bg, border) for k, icon, fc, bg, border in corpus_cfg if corpus_files.get(k)
            ]

            if non_empty_corpus:
                st.markdown("<div style='margin-top: 12px;'></div>", unsafe_allow_html=True)
                num_corpus_cols = min(len(non_empty_corpus), 4)
                corpus_cols = st.columns(num_corpus_cols)
                for col, (bucket, icon, font_color, bg_color, border_color) in zip(
                    corpus_cols, non_empty_corpus, strict=False
                ):
                    items = corpus_files[bucket]
                    with col:
                        st.markdown(
                            f"""
<div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 12px; padding: 15px; height: 350px; overflow-y: auto;">
    <h4 style="margin-top:0; color:{font_color}; display:flex; align-items:center; gap:8px; border-bottom: 1px solid {border_color}; padding-bottom: 8px; margin-bottom: 12px;">
        <span>{icon}</span> {bucket.capitalize()} ({len(items)})
    </h4>
    {get_corpus_list_html(items, bucket, font_color)}
</div>
""",
                            unsafe_allow_html=True,
                        )
            elif st.session_state.get("_lb_corpus_token"):
                st.caption("📁 No Corpus files found for this member in the selected date range.")
            else:
                st.caption("📁 Login to Corpus (sidebar) to view file contributions.")

            st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)


def _render_specific_team_analytics(
    team_name: str, project_name: str, member_rows: list[dict], totals: dict, raw_results: list[dict]
) -> None:
    """Detailed analytics view for a specific team."""
    st.subheader(f"🎯 Detailed View: {team_name}")
    if project_name:
        st.caption(f"Project: {project_name}")

    # 1. Team Metrics Dashboard
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Commits", totals.get("Total Commits", 0))
    m2.metric("MR Merged", totals.get("MR Merged", 0))
    m3.metric("MR Open", totals.get("MR Open", 0))
    m4.metric("MR Closed", totals.get("MR Closed", 0))
    m5.metric("Issues Raised", totals.get("Issues Raised", 0))
    m6.metric("Issues Closed", totals.get("Issues Closed", 0))

    # 2. Individual User Performance
    st.markdown("#### 👤 Individual User Performance")
    user_perf_cols = [
        "Username",
        "Status",
        "Error",
        "Total Commits",
        "Issues Raised",
        "Issues Closed",
        "MR Created",
        "MR Merged",
        "MR Open",
        "MR Closed",
        "Score",
    ]
    if member_rows:
        df_users = pd.DataFrame(member_rows)
        # Ensure all columns exist
        for col in user_perf_cols:
            if col not in df_users.columns:
                df_users[col] = 0
        st.dataframe(df_users[user_perf_cols], width="stretch", hide_index=True)
    else:
        st.info("No member data available.")

    # 3. Activity Feed (MRs & Issues)
    st.markdown("#### 📑 Activity Feed")
    activity_data = []

    for user_res in raw_results:
        if not user_res or not isinstance(user_res, dict):
            continue
        if user_res.get("status") != "Success":
            continue

        data = user_res.get("data", {})
        username = user_res.get("username", "unknown")

        # MRs
        for mr in data.get("mrs", []):
            activity_data.append(
                {
                    "Date": mr.get("created_at")[:10] if mr.get("created_at") else "—",
                    "Type": "Merge Request",
                    "User": username,
                    "Title": mr.get("title", "—"),
                    "Status": str(mr.get("state", "—")).capitalize(),
                    "Link": mr.get("web_url", "#"),
                }
            )

        # Issues
        for issue in data.get("issues", []):
            activity_data.append(
                {
                    "Date": issue.get("created_at")[:10] if issue.get("created_at") else "—",
                    "Type": "Issue",
                    "User": username,
                    "Title": issue.get("title", "—"),
                    "Status": str(issue.get("state", "—")).capitalize(),
                    "Link": issue.get("web_url", "#"),
                }
            )

    if activity_data:
        df_activity = pd.DataFrame(activity_data).sort_values("Date", ascending=False)
        st.dataframe(
            df_activity,
            column_config={
                "Link": st.column_config.LinkColumn("GitLab Link"),
            },
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No recent MRs or Issues found for this team.")


# ---------------------------------------------------------------------------
# UI: Overall Ranking
# ---------------------------------------------------------------------------


def _render_overall_ranking(team_data: dict) -> None:
    """Ranked ranking table + bar chart."""
    st.subheader("🏆 Overall Batch Analytics and Ranking")

    lb_rows = [
        {
            "Team": tn,
            "Project": meta.get("project_name", "—"),
            "Team Score": totals["Team Score"],
            "Total Commits": totals["Total Commits"],
            "MR Merged": totals["MR Merged"],
            "MR Created": totals["MR Created"],
            "MR Assigned": totals.get("MR Assigned", 0),
            "Issues Closed": totals["Issues Closed"],
            "Issues Raised": totals["Issues Raised"],
            "Issues Assigned": totals.get("Issues Assigned", 0),
        }
        for tn, (meta, _, totals) in team_data.items()
    ]
    df_lb = pd.DataFrame(lb_rows).sort_values("Team Score", ascending=False).reset_index(drop=True)
    df_lb.insert(0, "Rank", range(1, len(df_lb) + 1))
    st.dataframe(df_lb, width="stretch", hide_index=True)
    st.divider()


def _build_ranking_rows(team_data: dict) -> list[dict]:
    """Create sorted ranking rows from already aggregated team totals."""
    rows = []
    for team_name, (_, _, totals) in team_data.items():
        rows.append(
            {
                "Team Name": team_name,
                "Total Score": totals.get("Team Score", 0),
                "Total Commits": totals.get("Total Commits", 0),
                "MRs Merged": totals.get("MR Merged", 0),
                "Issues Closed": totals.get("Issues Closed", 0),
            }
        )

    rows.sort(key=lambda x: x["Total Score"], reverse=True)
    ranked_rows = []
    for idx, row in enumerate(rows, start=1):
        ranked_rows.append(
            {
                "Rank": idx,
                "Badge": "",
                **row,
            }
        )
    return ranked_rows


def _build_individual_rows(team_data: dict) -> list[dict]:
    """Flatten all members across teams into a ranked list with achievement badges."""
    all_members: list[dict] = []
    for team_name, (_, member_rows, _) in team_data.items():
        for row in member_rows:
            if row.get("Status") != "Success":
                continue
            all_members.append(
                {
                    "Username": row.get("Username", "unknown"),
                    "Name": row.get("Name", ""),
                    "Global Username": row.get("Global Username", ""),
                    "Global Email": row.get("Global Email", ""),
                    "Date of Joining": row.get("Date of Joining", ""),
                    "Team Name": team_name,
                    "Total Commits": row.get("Total Commits", 0),
                    "MRs Merged": row.get("MR Merged", 0),
                    "Issues Closed": row.get("Issues Closed", 0),
                    "Score": row.get("Score", 0),
                    "Time Spent": row.get("Time Spent", "0 min"),
                    "time_spent_seconds": row.get("time_spent_seconds", 0),
                    "Badge": "",
                }
            )

    all_members.sort(key=lambda x: x["Score"], reverse=True)

    # Track badges per member (max 3 each)
    MAX_BADGES = 3
    member_badges: dict[str, list[str]] = {m["Username"]: [] for m in all_members}

    def _can_badge(username: str) -> bool:
        return len(member_badges[username]) < MAX_BADGES

    def _add_badge(username: str, badge_name: str) -> None:
        member_badges[username].append(badge_name)

    # --- Team Player: highest scorer in each team ---
    teams_seen: set[str] = set()
    for m in all_members:
        team = m["Team Name"]
        if team not in teams_seen and m["Score"] > 0:
            _add_badge(m["Username"], "team_player")
            teams_seen.add(team)

    # --- Global achievement badges (a person can hold multiple) ---
    def _best_for(key: str, badge_name: str) -> None:
        for m in sorted(all_members, key=lambda x: x[key], reverse=True):
            if not _can_badge(m["Username"]):
                continue
            if badge_name in member_badges[m["Username"]]:
                continue
            if m[key] > 0:
                _add_badge(m["Username"], badge_name)
                return

    def _best_consistency(badge_name: str) -> None:
        candidates = [
            m
            for m in all_members
            if _can_badge(m["Username"])
            and badge_name not in member_badges[m["Username"]]
            and m["Total Commits"] > 0
            and m["MRs Merged"] > 0
            and m["Issues Closed"] > 0
        ]
        if not candidates:
            return
        best = min(
            candidates,
            key=lambda m: (
                statistics.stdev([m["Total Commits"], m["MRs Merged"], m["Issues Closed"]])
                / max(statistics.mean([m["Total Commits"], m["MRs Merged"], m["Issues Closed"]]), 1)
            ),
        )
        _add_badge(best["Username"], badge_name)

    _best_for("Score", "sprint_star")
    _best_for("Total Commits", "top_committer")
    _best_for("MRs Merged", "merge_master")
    # hackathon_hero: highest combined total
    for m in sorted(
        all_members,
        key=lambda x: x["Total Commits"] + x["MRs Merged"] + x["Issues Closed"],
        reverse=True,
    ):
        if (
            _can_badge(m["Username"])
            and "hackathon_hero" not in member_badges[m["Username"]]
            and (m["Total Commits"] + m["MRs Merged"] + m["Issues Closed"]) > 0
        ):
            _add_badge(m["Username"], "hackathon_hero")
            break
    _best_consistency("consistency_champ")

    # Write badges back to member dicts (list instead of single string)
    for m in all_members:
        m["Badges"] = member_badges[m["Username"]]

    # Assign serial numbers
    for idx, m in enumerate(all_members, start=1):
        m["S.No"] = idx

    return all_members


def _load_rank_badge_svg(rank: int) -> str:
    """Load badge SVG markup for ranks 1-6 from assets; otherwise return empty."""
    if rank < 1 or rank > 6:
        return ""

    repo_root = Path(__file__).resolve().parent.parent
    candidate_dirs = [
        repo_root / "badges",
        repo_root / "assets" / "badges",
        Path.home() / "Downloads" / "final badges",
        Path.home() / "Downloads" / "badges svg",
        Path.home() / "Downloads",
    ]

    explicit_names = [
        f"rank{rank}.svg",
        f"rank{rank} 1.svg",
        f"rank{rank} 2.svg",
    ]

    for folder in candidate_dirs:
        if not folder.exists():
            continue

        for name in explicit_names:
            badge_path = folder / name
            if badge_path.exists():
                try:
                    return badge_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fallback for any alternate exported name like rank1_final.svg
        for badge_path in sorted(folder.glob(f"rank{rank}*.svg")):
            try:
                return badge_path.read_text(encoding="utf-8")
            except Exception:
                continue

    return ""


def _load_individual_badge_svg(badge_name: str) -> str:
    """Load badge SVG markup by achievement name from assets/badges/."""
    if not badge_name:
        return ""
    repo_root = Path(__file__).resolve().parent.parent
    badge_path = repo_root / "assets" / "badges" / f"{badge_name}.svg"
    if badge_path.exists():
        try:
            return badge_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _render_ranking_table_html(ranked_rows: list[dict]) -> None:
    """Render ranking table with SVG badges using custom HTML/CSS."""
    table_rows: list[str] = []
    for row in ranked_rows:
        rank = int(row.get("Rank", 0))
        badge_svg = _load_rank_badge_svg(rank)

        if badge_svg:
            badge_html = f'<div class="lb-badge">{badge_svg}</div>'
        else:
            badge_html = ""

        table_rows.append(
            "<tr>"
            f'<td class="lb-rank">{rank}</td>'
            f'<td class="lb-badge-cell">{badge_html}</td>'
            f'<td class="lb-team">{escape(str(row.get("Team Name", "")))}</td>'
            f'<td class="lb-num">{int(row.get("Total Score", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Total Commits", 0))}</td>'
            f'<td class="lb-num">{int(row.get("MRs Merged", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Issues Closed", 0))}</td>'
            "</tr>"
        )

    html_table = f"""
<style>
.lb-rank-wrap {{
  width: 100%;
  overflow-x: auto;
}}
.lb-rank-table {{
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  background: rgba(18, 22, 30, 0.88);
  border: 1px solid rgba(120, 129, 149, 0.35);
  border-radius: 14px;
  overflow: hidden;
}}
.lb-rank-table thead th {{
  text-align: left;
  font-size: 17px;
  font-weight: 700;
  padding: 18px 16px;
  border-bottom: 1px solid rgba(120, 129, 149, 0.35);
  color: #e6edf7;
  letter-spacing: 0.01em;
  background: rgba(28, 33, 46, 0.95);
  white-space: nowrap;
}}
.lb-rank-table tbody td {{
  font-size: 18px;
  font-weight: 500;
  padding: 16px;
  border-bottom: 1px solid rgba(120, 129, 149, 0.24);
  color: #d9e1ee;
  vertical-align: middle;
}}
.lb-rank-table tbody tr:last-child td {{
  border-bottom: none;
}}
.lb-rank {{
  width: 80px;
  font-weight: 700;
  color: #f4f7ff;
}}
.lb-badge-cell {{
  min-width: 140px;
}}
.lb-badge {{
  width: 120px;
  min-height: 64px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}}
.lb-badge svg {{
  width: 120px;
  height: auto;
  display: block;
}}
.lb-badge-label {{
  font-size: 11px;
  font-weight: 600;
  color: #a0b4d0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}}
.lb-badges-row {{
  display: inline-flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}}
.lb-team {{
  min-width: 220px;
  font-weight: 600;
}}
.lb-num {{
  min-width: 120px;
  white-space: nowrap;
}}
</style>
<div class="lb-rank-wrap">
  <table class="lb-rank-table">
    <thead>
      <tr>
        <th>Rank</th>
        <th>Badge</th>
        <th>Team Name</th>
        <th>Total Score</th>
        <th>Total Commits</th>
        <th>MRs Merged</th>
        <th>Issues Closed</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
</div>
"""
    st.markdown(html_table, unsafe_allow_html=True)


def _render_individual_table_html(individual_rows: list[dict]) -> None:
    """Render individual member ranking table with achievement badges."""
    _badge_display_names = {
        "team_player": "Team Player",
        "sprint_star": "Sprint Star",
        "top_committer": "Top Committer",
        "merge_master": "Merge Master",
        "hackathon_hero": "Hackathon Hero",
        "consistency_champ": "Consistency Champ",
    }

    table_rows: list[str] = []
    for row in individual_rows:
        badges = row.get("Badges", [])
        badge_parts: list[str] = []
        for badge_name in badges or []:
            svg = _load_individual_badge_svg(badge_name)
            if svg:
                label = _badge_display_names.get(badge_name, badge_name.replace("_", " ").title())
                badge_parts.append(
                    f'<div class="lb-badge">{svg}<span class="lb-badge-label">{escape(label or "")}</span></div>'
                )
        badge_html = f'<div class="lb-badges-row">{"".join(badge_parts)}</div>' if badge_parts else ""

        table_rows.append(
            "<tr>"
            f'<td class="lb-rank">{int(row.get("S.No", 0))}</td>'
            f'<td class="lb-badge-cell">{badge_html}</td>'
            f'<td class="lb-team">{escape(str(row.get("Name", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Username", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Global Username", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Team Name", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Date of Joining", "")))}</td>'
            f'<td class="lb-num">{int(row.get("Total Commits", 0))}</td>'
            f'<td class="lb-num">{int(row.get("MRs Merged", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Issues Closed", 0))}</td>'
            f'<td class="lb-num" style="color: #70b1ff; font-weight: 700;">{escape(str(row.get("Time Spent", "0 min")))}</td>'
            "</tr>"
        )

    html_table = f"""
<div class="lb-rank-wrap">
  <table class="lb-rank-table">
    <thead>
      <tr>
        <th>S.No</th>
        <th>Badge</th>
        <th>Name</th>
        <th>Username</th>
        <th>Global User</th>
        <th>Team Name</th>
        <th>DOJ</th>
        <th>Commits</th>
        <th>MRs</th>
        <th>Issues</th>
        <th>Time Spent</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
</div>
"""
    st.markdown(html_table, unsafe_allow_html=True)


def _render_ranking_page() -> None:
    """Ranking-only view that reuses previously computed summary rows."""
    st.markdown("### 🏅 Batch Ranking")
    st.caption("Structured ranking table with badge placeholders for top 6 teams.")

    ranked_rows = st.session_state.get("_lb_last_ranking_rows", [])
    if not ranked_rows:
        st.info("No ranking data available yet. Go to **Workspace**, run analysis, then return here.")
        return

    _render_ranking_table_html(ranked_rows)

    # ── Individual Member Rankings ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 👤 Individual Member Rankings")
    st.caption(
        "All members ranked by individual score. "
        "Achievement badges: sprint_star, top_committer, merge_master, "
        "team_player, hackathon_hero, consistency_champ."
    )

    individual_rows = st.session_state.get("_lb_last_individual_rows", [])
    if individual_rows:
        _render_individual_table_html(individual_rows)
    else:
        st.info("No individual data available yet.")

    # ── Score Comparison Chart ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Score Comparison")
    if ranked_rows:
        df_chart = pd.DataFrame(ranked_rows)
        # Map back to the expected columns for the chart
        if not df_chart.empty:
            chart_data = df_chart.rename(columns={"Team Name": "Team", "Total Score": "Team Score"})
            st.bar_chart(chart_data.set_index("Team")[["Team Score"]])


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def render_batch_analytics(client) -> None:
    """Main render function. Called from app.py with the GitLabClient instance."""
    _init_state()

    if "_lb_cached_results" not in st.session_state:
        st.session_state["_lb_cached_results"] = None
    if "_lb_last_filters" not in st.session_state:
        st.session_state["_lb_last_filters"] = None

    _render_corpus_login()

    if not st.session_state.get("_lb_corpus_token"):
        st.warning(
            "📻 **Corpus Audio Missing**: Please login with your Corpus credentials in the sidebar to include audio contributions in the batch analytics."
        )

    st.subheader("🏆 Batch Analytics and Ranking")
    st.markdown(
        "Create and manage teams, then run analytics to compare productivity scores.\n\n"
        "**Score formula:** `Commits × 1 + Merged MRs × 5 + Total MRs × 2 + Issues Closed × 3`"
    )

    # ── Scoped UI Restyling CSS ──────────────────────────────────────────
    # Removed temporarily for debugging
    pass

    # Load data

    batches = get_all_batches()
    batch_names = ["All Batches"] + [b["name"] for b in batches]

    st.markdown("### 🎯 Data Filter")
    c1, c2, c3 = st.columns(3)

    with c1:
        selected_batch = st.selectbox(
            "Select Batch",
            options=batch_names,
            index=batch_names.index(st.session_state["_lb_selected_batch"])
            if st.session_state["_lb_selected_batch"] in batch_names
            else 0,
            key="_lb_batch_sel",
            help="Filter teams by batch.",
        )
        if selected_batch != st.session_state["_lb_selected_batch"]:
            st.session_state["_lb_selected_batch"] = selected_batch
            st.session_state["_lb_selected_teams"] = ["All Teams"]
            st.session_state["_lb_selected_member"] = "All Members"
            st.rerun()

    # Get teams for selected batch
    if not selected_batch:
        selected_batch = "All Batches"
    teams_in_batch = get_teams_by_batch(selected_batch)
    team_options = ["All Teams"] + [t["name"] for t in teams_in_batch]

    with c2:
        selected_teams = st.multiselect(
            "Select Team(s)",
            options=team_options,
            default=st.session_state["_lb_selected_teams"]
            if all(t in team_options for t in st.session_state["_lb_selected_teams"])
            else ["All Teams"],
            key="_lb_teams_sel",
            help="Select one or more teams, or 'All Teams' for an overall comparison.",
        )
        if selected_teams != st.session_state["_lb_selected_teams"]:
            st.session_state["_lb_selected_teams"] = selected_teams
            # Reset members list when teams change
            st.session_state["_lb_selected_members"] = ["All Members"]
            st.rerun()

    # Individual Selection - Gather members from all selected teams
    all_potential_members = []

    # Define which teams to pull members from
    if "All Teams" in selected_teams:
        teams_for_members = teams_in_batch
    else:
        teams_for_members = [t for t in teams_in_batch if t["name"] in selected_teams]

    for t in teams_for_members:
        team_members = get_members_by_team(t["name"], str(selected_batch))
        for m in team_members:
            # Format: Name (@username) [Team]
            label = f"{m['name']} (@{m['gitlab_username']}) [{t['name']}]"
            all_potential_members.append(label)

    member_options = ["All Members"] + sorted(all_potential_members)

    with c3:
        selected_members = st.multiselect(
            "Select Individual(s)",
            options=member_options,
            default=st.session_state["_lb_selected_members"]
            if all(m in member_options for m in st.session_state["_lb_selected_members"])
            else ["All Members"],
            key="_lb_members_sel",
            help="Select specific individuals across the selected teams. Leave as 'All Members' to analyze everyone.",
        )
        if selected_members != st.session_state["_lb_selected_members"]:
            st.session_state["_lb_selected_members"] = selected_members
            st.rerun()

    st.divider()

    # ── Page selector (Button Toggle) ────────────────────────────────────
    st.markdown('<div class="lb-toggle-container">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    current_page = st.session_state.get("_lb_page", "Workspace")

    with col1:
        if st.button(
            "Workspace",
            width="stretch",
            key="_btn_workspace",
            type="secondary" if current_page == "Batch Ranking" else "primary",
        ):
            st.session_state["_lb_page"] = "Workspace"
            st.rerun()

    with col2:
        if st.button(
            "Batch Ranking",
            width="stretch",
            key="_btn_ranking",
            type="secondary" if current_page == "Workspace" else "primary",
        ):
            st.session_state["_lb_page"] = "Batch Ranking"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    page = st.session_state["_lb_page"]
    st.divider()

    if page == "Batch Ranking":
        _render_ranking_page()
        return

    # Removed Sections 1 & 2 (Team creation/management)

    # ── Section 3: Analysis ───────────────────────────────────────────────
    # Only use teams corresponding to the current scope
    all_available_teams = get_all_teams_with_members()

    if "All Teams" in selected_teams:
        if selected_batch == "All Batches":
            teams_to_process = all_available_teams
        else:
            # All teams in a specific batch
            teams_to_process = [t for t in all_available_teams if t.get("batch_name") == selected_batch]
    else:
        # Specific multiple teams
        teams_to_process = [
            t
            for t in all_available_teams
            if t["team_name"] in selected_teams
            and (selected_batch == "All Batches" or t.get("batch_name") == selected_batch)
        ]

    # Further filter by members if needed
    if "All Members" not in selected_members and selected_members:
        # Extract usernames from labels: "Name (@username) [Team]"
        target_usernames = []
        for label in selected_members:
            if "(@" in label:
                username = label.split("(@")[1].split(")")[0]
                target_usernames.append(username)

        target_usernames_set = set(target_usernames)

        for t in teams_to_process:
            t["members"] = [m for m in t["members"] if m["username"] in target_usernames_set]

        # Remove teams that now have no selected members
        teams_to_process = [t for t in teams_to_process if t["members"]]

    if not teams_to_process:
        st.info("Add at least one team above to enable analysis.")
        return

    # Disable Run while an edit is active
    if st.session_state.get("edit_team_index") is not None:
        st.info("💡 Finish editing the team above before running analysis.")
        return

    # ── Date range filter ─────────────────────────────────────────────────
    since_iso, until_iso = _render_date_filter()

    # ── Run button ────────────────────────────────────────────────────────
    st.markdown('<div class="lb-run-btn">', unsafe_allow_html=True)
    run_button_clicked = st.button("▶️ Run Batch Analysis", type="primary", key="_lb_run_btn")
    st.markdown("</div>", unsafe_allow_html=True)
    if run_button_clicked:
        st.session_state["_lb_triggered"] = True

    if not st.session_state.get("_lb_triggered"):
        st.info("Click **▶️ Run Batch Analysis** to fetch data for all teams.")
        return

    if not teams_to_process:
        st.warning("No data found for the selected scope.")
        return

    # ── Cache key: fingerprint of current ALL teams configuration + date filters ────────────
    # We use ALL teams for the configuration key, so that changing the dropdown alone does not invalidate it.
    current_filters = {
        "teams": [
            {
                "team_name": t["team_name"],
                "project_name": t.get("project_name", ""),
                "members": sorted([m["username"] for m in t.get("members", []) if m.get("username")]),
            }
            for t in teams_to_process
        ],
        "since": since_iso,
        "until": until_iso,
    }

    cached_results = st.session_state.get("_lb_cached_results", {}) or {}
    last_filters = st.session_state.get("_lb_last_filters", {})

    needs_fetch = run_button_clicked
    if not cached_results:
        needs_fetch = True
    elif last_filters != current_filters:
        needs_fetch = True
    else:
        # Check if we already have the requested data
        for t in teams_to_process:
            if t["team_name"] not in cached_results:
                needs_fetch = True
                break

    # ── Team result placeholders — created here so they appear in the right position ──
    st.markdown("### 📊 Team Results")
    team_placeholders = {t["team_name"]: st.empty() for t in teams_to_process}

    if not needs_fetch:
        team_data = cached_results
        for team_name in [t["team_name"] for t in teams_to_process]:
            if team_name in team_data:
                meta, member_rows, totals = team_data[team_name]
                with team_placeholders[team_name].container():
                    _render_team_result(
                        team_name, meta.get("project_name", ""), member_rows, totals, key_prefix=f"{team_name}_c"
                    )
    else:
        # ── Fetch ─────────────────────────────────────────────────────────
        # Retain existing cached results if we are just adding to it
        team_data = cached_results if not run_button_clicked and last_filters == current_filters else {}
        all_phase1_results: list = []  # flat list of all per-user phase-1 results for phase 2

        # ── Phase 1: projects, MRs, issues, timelogs (GraphQL, fast) ─────────
        progress = st.progress(0, text="Fetching profile data (projects, MRs, issues)…")

        for idx, team in enumerate(teams_to_process):
            team_name = team["team_name"]
            usernames = [m["username"] for m in team.get("members", []) if m.get("username")]

            if not usernames:
                team_data[team_name] = (team, [], _aggregate_team_totals([]))
                progress.progress((idx + 1) / len(teams_to_process), text=f"Skipped: {team_name}")
                continue

            with st.spinner(f"Fetching **{team_name}** profile data ({len(usernames)} member(s))…"):
                try:
                    overrides = {}
                    for m in team.get("members", []):
                        uname = m.get("username")
                        if not uname:
                            continue
                        ov: dict = {}
                        doj = m.get("date_of_joining")
                        if doj:
                            ov["time_since"] = doj
                        ge = m.get("global_email") or ""
                        if ge:
                            ov["override_email"] = ge
                        gu = m.get("global_username") or ""
                        if gu:
                            ov["override_username"] = gu
                        if ov:
                            overrides[uname] = ov

                    results = process_batch_users_no_commits(
                        client,
                        usernames,
                        since=since_iso,
                        until=until_iso,
                        overrides=overrides,
                    )
                except Exception as exc:
                    st.warning(f"⚠️ Could not fetch data for **{team_name}**: {exc}")
                    results = []

            all_phase1_results.extend(results)

            member_rows = []
            for r in results:
                if not r:
                    continue
                mrow = _extract_member_row(r)
                found_meta: dict[str, Any] = next(
                    (m for m in team.get("members", []) if m["username"] == r.get("username")), {}
                )
                mrow.update(
                    {
                        "Name": found_meta.get("name", mrow.get("Name", "")),
                        "corpus_username": found_meta.get("corpus_username", ""),
                        "Global Username": found_meta.get("global_username", ""),
                        "Global Email": found_meta.get("global_email", ""),
                        "Date of Joining": found_meta.get("date_of_joining", ""),
                        "corpus_files": {"audio": [], "image": [], "video": [], "file": []},
                    }
                )
                member_rows.append(mrow)

            # ── Corpus media fetch (independent of commits, done in phase 1) ──
            corpus_client = st.session_state.get("_lb_corpus_client")
            if corpus_client:
                with st.spinner(f"Fetching Corpus files for **{team_name}**…"):
                    members_with_corpus = [
                        {"username": m.get("username", ""), "corpus_username": m.get("corpus_username", "")}
                        for m in team.get("members", [])
                    ]
                    corpus_since = since_iso[:10] if since_iso else None
                    corpus_until = until_iso[:10] if until_iso else None
                    corpus_media_map = _fetch_corpus_media_for_team(
                        corpus_client, members_with_corpus, corpus_since, corpus_until
                    )
                    for mrow in member_rows:
                        gl_user = mrow.get("Username", "")
                        mrow["corpus_files"] = corpus_media_map.get(
                            gl_user, {"audio": [], "image": [], "video": [], "file": []}
                        )

            # Attendance with empty commits (recalculated after phase 2)
            for mrow in member_rows:
                activity_map = _get_daily_activity_counts(
                    mrow.get("mrs_list", []),
                    mrow.get("issues_list", []),
                    mrow.get("commits_list", []),
                    corpus_files=mrow.get("corpus_files", {}),
                )
                joining_date_str = mrow.get("Date of Joining")
                joining_date = None
                if joining_date_str:
                    try:
                        joining_date = dateutil.parser.parse(joining_date_str).date()
                    except Exception:
                        pass
                active_days, total_days, consistency_pct, working_days, attendance_pct = _get_contribution_index(
                    activity_map, mrow.get("Username"), joining_date=joining_date
                )
                mrow["Active Days"] = active_days
                mrow["Total Days"] = total_days
                mrow["Consistency %"] = consistency_pct
                mrow["Attendance %"] = attendance_pct
                mrow["Working Days"] = working_days

            totals = _aggregate_team_totals(member_rows)
            team_data[team_name] = (team, member_rows, totals)

            # Render phase 1 results immediately — MRs, issues, groups visible now; commits show 0
            with team_placeholders[team_name].container():
                _render_team_result(
                    team_name, team.get("project_name", ""), member_rows, totals, key_prefix=f"{team_name}_p1"
                )

            progress.progress((idx + 1) / len(teams_to_process), text=f"Done (no commits): {team_name}")

        progress.empty()

        if not team_data:
            st.error("No team data could be fetched. Check your GitLab connection.")
            return

        # Show loading indicator while commits are fetched
        commits_loading = st.info("⏳ Loading commits for all teams… Commit counts and scores will update shortly.")

        # ── Phase 2: commits for all teams at once (REST, slower) ────────────
        with st.spinner("Fetching commits for all teams…"):
            commits_map = fetch_batch_commits(client, all_phase1_results)

        # Inject commits into every member row and recalculate scores + attendance
        for team_name in list(team_data.keys()):
            team, member_rows, _ = team_data[team_name]
            for mrow in member_rows:
                username = mrow.get("Username", "")
                if username in commits_map:
                    all_commits, commit_stats = commits_map[username]
                    mrow["Total Commits"] = commit_stats.get("total", 0)
                    mrow["Morning Commits"] = commit_stats.get("morning_commits", 0)
                    mrow["Afternoon Commits"] = commit_stats.get("afternoon_commits", 0)
                    mrow["commits_list"] = all_commits
                    mrow["Score"] = _calculate_score(
                        commit_stats.get("total", 0),
                        mrow.get("MR Merged", 0),
                        mrow.get("MR Created", 0),
                        mrow.get("Issues Closed", 0),
                    )

            # Recalculate attendance now that commits_list is populated
            for mrow in member_rows:
                activity_map = _get_daily_activity_counts(
                    mrow.get("mrs_list", []),
                    mrow.get("issues_list", []),
                    mrow.get("commits_list", []),
                    corpus_files=mrow.get("corpus_files", {}),
                )
                joining_date_str = mrow.get("Date of Joining")
                joining_date = None
                if joining_date_str:
                    try:
                        joining_date = dateutil.parser.parse(joining_date_str).date()
                    except Exception:
                        pass
                active_days, total_days, consistency_pct, working_days, attendance_pct = _get_contribution_index(
                    activity_map, mrow.get("Username"), joining_date=joining_date
                )
                mrow["Active Days"] = active_days
                mrow["Total Days"] = total_days
                mrow["Consistency %"] = consistency_pct
                mrow["Attendance %"] = attendance_pct
                mrow["Working Days"] = working_days

            totals = _aggregate_team_totals(member_rows)
            team_data[team_name] = (team, member_rows, totals)

            # Replace phase-1 content with full results (commits now populated)
            team_placeholders[team_name].empty()
            with team_placeholders[team_name].container():
                _render_team_result(
                    team_name, team.get("project_name", ""), member_rows, totals, key_prefix=f"{team_name}_p2"
                )

        # Clear loading indicator
        commits_loading.empty()

        # Only update cache if we processed something new.
        # Don't erase the rest of the cache if we only fetched a sub-team.
        for k, v in team_data.items():
            cached_results[k] = v

        st.session_state["_lb_cached_results"] = cached_results
        st.session_state["_lb_last_filters"] = current_filters

        # Cache ranking rows for the Ranking page
        st.session_state["_lb_last_ranking_rows"] = _build_ranking_rows(st.session_state["_lb_cached_results"])
        st.session_state["_lb_last_individual_rows"] = _build_individual_rows(st.session_state["_lb_cached_results"])

    if "All Teams" in selected_teams or len(selected_teams) > 1:
        _render_overall_ranking(team_data)

    # ── Export ────────────────────────────────────────────────────────────
    st.subheader("📥 Export Report")
    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    filename_full = f"batch_analytics_{now_ist.strftime('%Y-%m-%d')}.xlsx"
    filename_indiv = f"individual_metrics_{now_ist.strftime('%Y-%m-%d')}.xlsx"

    try:
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            st.download_button(
                label="⬇️ Download Full Report (Excel)",
                data=_build_excel_export(team_data),
                file_name=filename_full,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_full_report",
            )
        with col_ex2:
            st.download_button(
                label="⬇️ Download Individual Metrics (Excel)",
                data=_build_individual_metrics_excel_export(team_data),
                file_name=filename_indiv,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_indiv_report",
            )
    except Exception as exc:
        st.error(f"Could not generate Excel export: {exc}")
