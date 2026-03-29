"""
Team Leaderboard Mode — Dynamic Team Creation + Edit
------------------------------------------------------
Supports creating and editing teams via UI with full session state persistence.
Fetches analytics via process_batch_users() and renders a ranked leaderboard.

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

import dateutil.parser
import pandas as pd
import streamlit as st

from gitlab_utils.batch import process_batch_users
from modes.batch_mode import DEFAULT_ICFAI_USERS, DEFAULT_RCTS_USERS

# ---------------------------------------------------------------------------
# Default Teams (pre-configured)
# ---------------------------------------------------------------------------

BACKEND_TEAMS: list[dict] = [
    {
        "team_name": "Dev 3",
        "project_name": "Dev 3",
        "members": [
            {"name": "Sai Krishna", "username": "saikrishna_b", "user_id": None},
            {"name": "Bhavitha", "username": "MohanaSriBhavitha", "user_id": None},
            {
                "name": "Madavarapu Sai Harshavardhan",
                "username": "Saiharshavardhan",
                "user_id": None,
            },
        ],
    },
    {
        "team_name": "Trinity",
        "project_name": "Trinity",
        "members": [
            {"name": "Praneeth Ashish", "username": "praneethashish", "user_id": None},
            {"name": "Vaishnavi Prabhala", "username": "vai5h", "user_id": None},
            {"name": "Greeshma Kanukunta", "username": "kanukuntagreeshma2004", "user_id": None},
        ],
    },
    {
        "team_name": "Sudo",
        "project_name": "Sudo",
        "members": [
            {"name": "Balannagari Vandana Reddy", "username": "vandana1735", "user_id": None},
            {"name": "Rajuldev Vandana", "username": "vandana_rajuldev", "user_id": None},
            {"name": "Challa lakshmi Pavani", "username": "lakshmipavani_20", "user_id": None},
        ],
    },
    {
        "team_name": "Trishul",
        "project_name": "Trishul",
        "members": [
            {"name": "Mukthananad Reddy", "username": "Mukthanand21", "user_id": None},
            {"name": "Lanke Shanmukha Varma", "username": "Shanmukh16", "user_id": None},
            {"name": "Maddula Rushika Sritha", "username": "Rushika_1105", "user_id": None},
        ],
    },
    {
        "team_name": "BrainStorm",
        "project_name": "BrainStorm",
        "members": [
            {"name": "Daliboina satish", "username": "satish05", "user_id": None},
            {
                "name": "Damanagari Sathwika",
                "username": "Sathwikareddy_Damanagari",
                "user_id": None,
            },
            {"name": "C.Sahasra", "username": "Sahasraa", "user_id": None},
        ],
    },
    {
        "team_name": "Core",
        "project_name": "Core",
        "members": [
            {"name": "Abhilash", "username": "Abhilash653", "user_id": None},
            {"name": "kanda swarna rathna madhuri", "username": "swarna_4539", "user_id": None},
            {"name": "Laxman Reddy", "username": "laxmanreddypatlolla", "user_id": None},
        ],
    },
    {
        "team_name": "Magnum",
        "project_name": "Magnum",
        "members": [
            {"name": "Lagichetty Kushal", "username": "LagichettyKushal", "user_id": None},
            {"name": "Lakshy Yarlagadda", "username": "Lakshy", "user_id": None},
            {"name": "Nagi Reddy Pavani", "username": "pavaninagireddi", "user_id": None},
        ],
    },
    {
        "team_name": "TrioForce",
        "project_name": "TrioForce",
        "members": [
            {"name": "Aravindswamy", "username": "aravindswamy", "user_id": None},
            {"name": "Suma Reddy", "username": "Suma2304", "user_id": None},
            {"name": "Koushik Reddy", "username": "koushik_18", "user_id": None},
        ],
    },
    {
        "team_name": "Techops",
        "project_name": "Techops",
        "members": [
            {"name": "Prabhu kumari", "username": "kumari123", "user_id": None},
            {"name": "Habiba", "username": "Habeebunissa", "user_id": None},
            {"name": "Chesetti Sai Jeevana Jyothi", "username": "jeevana_31", "user_id": None},
        ],
    },
    {
        "team_name": "Mind ops",
        "project_name": "Mind ops",
        "members": [
            {"name": "Bhaskar", "username": "Bhaskar_Battula", "user_id": None},
            {"name": "Sai Teja", "username": "saiteja3005", "user_id": None},
            {"name": "Satya Pranavanadh", "username": "Pranav_rs", "user_id": None},
        ],
    },
    {
        "team_name": "code dev",
        "project_name": "code dev",
        "members": [
            {"name": "", "username": "klaxmi1908", "user_id": None},
            {"name": "", "username": "prav2702", "user_id": None},
        ],
    },
    {
        "team_name": "spk",
        "project_name": "spk",
        "members": [
            {"name": "", "username": "Pavani_Pothuganti", "user_id": None},
            {"name": "", "username": "SandhyaRani_111", "user_id": None},
            {"name": "", "username": "Kaveri_Mamidi", "user_id": None},
        ],
    },
]

# ---------------------------------------------------------------------------
# Session State Bootstrap
# ---------------------------------------------------------------------------


def _init_state() -> None:
    """Initialise all session-state keys used by this module. Safe to call repeatedly."""
    defaults: dict = {
        "teams": copy.deepcopy(BACKEND_TEAMS),  # Pre-load with default teams
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
        "_lb_selected_team": "All Teams",
        "_lb_page": "Workspace",
        "_lb_last_ranking_rows": [],
        "_lb_cached_results": None,
        "_lb_last_filters": None,
        "_lb_selected_view_team": "All Teams",
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


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
            "Error": result.get("error", "Unknown error"),
            "mrs_list": [],
            "issues_list": [],
            "commits_list": [],
        }

    data = result.get("data", {})
    c = data.get("commit_stats", {})
    m = data.get("mr_stats", {})
    i = data.get("issue_stats", {})

    total_commits = c.get("total", 0)
    total_mrs = m.get("total", 0)
    merged_mrs = m.get("merged", 0)
    issues_closed = i.get("closed", 0)

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
        "mrs_list": data.get("mrs", []),
        "issues_list": data.get("issues", []),
        "commits_list": data.get("commits", []),
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
    }
    for row in member_rows:
        for key in totals:
            src = "Score" if key == "Team Score" else key
            totals[key] += row.get(src, 0)
    return totals


def _team_name_exists(name: str, exclude_index: int | None = None) -> bool:
    """Return True if a team with this name already exists (optionally skipping one index)."""
    for idx, t in enumerate(st.session_state["teams"]):
        if idx == exclude_index:
            continue
        if t["team_name"].strip().lower() == name.strip().lower():
            return True
    return False


def _build_excel_export(team_data: dict) -> bytes:
    """Multi-sheet Excel: Sheet 1 = leaderboard, Sheet N = per-team member details."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        lb_rows = [
            {"Team": tn, "Project": meta.get("project_name", ""), **totals}
            for tn, (meta, _, totals, *_) in team_data.items()
        ]
        (
            pd.DataFrame(lb_rows)
            .sort_values("Team Score", ascending=False)
            .to_excel(writer, index=False, sheet_name="Leaderboard")
        )
        for team_name, (_, member_rows, _, *_) in team_data.items():
            pd.DataFrame(member_rows).to_excel(writer, index=False, sheet_name=team_name[:31])
    return output.getvalue()


# ---------------------------------------------------------------------------
# UI: JSON Bulk Upload
# ---------------------------------------------------------------------------


def _validate_json_teams(raw: dict) -> tuple[list[dict] | None, str]:
    """
    Validate parsed JSON against the expected teams schema.
    Returns (teams_list, "") on success or (None, error_message) on failure.
    """
    if not isinstance(raw, dict) or "teams" not in raw:
        return None, 'JSON must be an object containing a "teams" key.'

    teams = raw["teams"]
    if not isinstance(teams, list):
        return None, '"teams" must be a list.'
    if not teams:
        return None, '"teams" list is empty.'

    existing_names = {t["team_name"].strip().lower() for t in st.session_state["teams"]}
    seen_names: set[str] = set()

    for ti, team in enumerate(teams, start=1):
        tname = team.get("team_name", "")
        pname = team.get("project_name", "")
        members = team.get("members", [])

        if not isinstance(tname, str) or not tname.strip():
            return None, f'Team #{ti}: "team_name" is missing or empty.'
        if not isinstance(pname, str) or not pname.strip():
            return None, f'Team #{ti} ({tname}): "project_name" is missing or empty.'
        if not isinstance(members, list) or not members:
            return None, f'Team #{ti} ({tname}): "members" must be a non-empty list.'

        norm = tname.strip().lower()
        if norm in existing_names:
            return None, f'Team "{tname}" already exists in the current session.'
        if norm in seen_names:
            return None, f'Duplicate team name "{tname}" found in the uploaded file.'
        seen_names.add(norm)

        seen_usernames: set[str] = set()
        for mi, member in enumerate(members, start=1):
            mname = member.get("name", "")
            musername = member.get("username", "")
            if not isinstance(musername, str) or not musername.strip():
                return None, (f'Team "{tname}", member #{mi}: "username" is missing or empty.')
            if not isinstance(mname, str):
                return None, (f'Team "{tname}", member #{mi}: "name" must be a string.')
            ukey = musername.strip().lower()
            if ukey in seen_usernames:
                return None, (f'Team "{tname}": duplicate username "{musername}".')
            seen_usernames.add(ukey)

    return teams, ""


def _render_json_upload() -> None:
    """
    Render the JSON bulk-upload section inside an expander.
    Appends validated teams to st.session_state["teams"].
    """
    import json

    with st.expander("📂 Upload JSON File", expanded=True):
        st.markdown(
            "Upload a `.json` file to import multiple teams at once. Existing teams will **not** be overwritten."
        )
        _SAMPLE_JSON = (
            "{"
            + '\n  "teams": ['
            + "\n    {"
            + '\n      "team_name": "Team Alpha",'
            + '\n      "project_name": "Project A",'
            + '\n      "members": ['
            + '\n        { "name": "John", "username": "john123" }'
            + "\n      ]"
            + "\n    }"
            + "\n  ]"
            + "\n}"
        )
        st.code(_SAMPLE_JSON, language="json")

        uploaded = st.file_uploader(
            "Choose a JSON file",
            type=["json"],
            key="_lb_json_uploader",
            label_visibility="collapsed",
        )

        if uploaded is None:
            return

        st.caption(f"📄 Uploaded: **{uploaded.name}**")

        raw_bytes = uploaded.read()
        if not raw_bytes:
            st.error("The uploaded file is empty.")
            return

        try:
            raw_data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Could not parse JSON: {exc}")
            return

        teams_to_add, err = _validate_json_teams(raw_data)
        if err:
            st.error(f"Validation error: {err}")
            return

        # Normalise member dicts (ensure user_id key exists)
        clean_teams = [
            {
                "team_name": t["team_name"].strip(),
                "project_name": t["project_name"].strip(),
                "members": [
                    {
                        "name": m.get("name", "").strip(),
                        "username": m["username"].strip(),
                        "user_id": m.get("user_id") or None,
                    }
                    for m in t["members"]
                ],
            }
            for t in teams_to_add or []
        ]

        st.session_state["teams"].extend(clean_teams)
        st.session_state["_lb_show_upload_form"] = False
        st.session_state["_lb_triggered"] = False
        st.success(
            f"✅ {len(clean_teams)} team(s) imported successfully: "
            + ", ".join(f"**{t['team_name']}**" for t in clean_teams)
        )
        st.rerun()


# ---------------------------------------------------------------------------
# UI: Create Team Form
# ---------------------------------------------------------------------------


def _render_create_team_form() -> None:
    """Expandable form for creating a brand-new team."""
    # Don't show either form while an edit is active
    if st.session_state.get("edit_team_index") is not None:
        return

    # Two-button header: Create | Upload JSON
    btn_col1, btn_col2 = st.columns([1, 1])

    with btn_col1:
        create_label = "✖ Cancel" if st.session_state["_lb_show_create_form"] else "➕ Create New Team"
        if st.button(create_label, key="_lb_toggle_form", use_container_width=True):
            st.session_state["_lb_show_create_form"] = not st.session_state["_lb_show_create_form"]
            st.session_state["_lb_show_upload_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    with btn_col2:
        upload_label = "✖ Cancel Upload" if st.session_state["_lb_show_upload_form"] else "📂 Add All Teams Using JSON"
        if st.button(upload_label, key="_lb_toggle_upload", use_container_width=True):
            st.session_state["_lb_show_upload_form"] = not st.session_state["_lb_show_upload_form"]
            st.session_state["_lb_show_create_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    # Show whichever panel is active
    if st.session_state["_lb_show_upload_form"]:
        _render_json_upload()
        return

    if not st.session_state["_lb_show_create_form"]:
        return

    st.markdown("#### 🆕 New Team")
    col_a, col_b = st.columns(2)
    with col_a:
        team_name = st.text_input("Team Name *", key="_lb_new_team_name", placeholder="e.g. Team Alpha")
    with col_b:
        project_name = st.text_input("Project Name", key="_lb_new_project_name", placeholder="e.g. Project Phoenix")

    st.markdown("##### ➕ Add Members")
    mc1, mc2, mc3 = st.columns([2, 2, 1])
    with mc1:
        m_name = st.text_input("Member Name", key="_lb_c_m_name", placeholder="John Doe")
    with mc2:
        m_user = st.text_input("GitLab Username *", key="_lb_c_m_user", placeholder="john_doe")
    with mc3:
        m_id = st.number_input("User ID (opt.)", key="_lb_c_m_id", min_value=0, step=1, value=0)

    if st.button("➕ Add Member", key="_lb_create_add_member"):
        if not m_user.strip():
            st.warning("GitLab Username is required.")
        elif m_user.strip().lower() in [x["username"].lower() for x in st.session_state["_lb_draft_members"]]:
            st.warning(f"**{m_user}** is already in the list.")
        else:
            st.session_state["_lb_draft_members"].append(
                {
                    "name": m_name.strip(),
                    "username": m_user.strip(),
                    "user_id": int(m_id) if m_id else None,
                }
            )
            st.rerun()

    if st.session_state["_lb_draft_members"]:
        st.markdown("**Members added so far:**")
        st.dataframe(
            pd.DataFrame(st.session_state["_lb_draft_members"]),
            use_container_width=True,
            hide_index=True,
        )
        rm_user = st.selectbox(
            "Remove a member",
            key="_lb_create_rm_select",
            options=["— select —"] + [m["username"] for m in st.session_state["_lb_draft_members"]],
        )
        if st.button("🗑 Remove Selected Member", key="_lb_create_rm_btn"):
            if rm_user != "— select —":
                st.session_state["_lb_draft_members"] = [
                    m for m in st.session_state["_lb_draft_members"] if m["username"] != rm_user
                ]
                st.rerun()
    else:
        st.info("No members added yet.")

    st.markdown("---")
    if st.button("💾 Save Team", type="primary", key="_lb_save_team"):
        if not team_name.strip():
            st.error("Team Name is required.")
        elif not st.session_state["_lb_draft_members"]:
            st.error("Add at least one member before saving.")
        elif _team_name_exists(team_name):
            st.error(f'A team named **"{team_name}"** already exists.')
        else:
            st.session_state["teams"].append(
                {
                    "team_name": team_name.strip(),
                    "project_name": project_name.strip(),
                    "members": list(st.session_state["_lb_draft_members"]),
                }
            )
            st.session_state["_lb_draft_members"] = []
            st.session_state["_lb_show_create_form"] = False
            st.session_state["_lb_triggered"] = False
            st.session_state["_lb_cached_results"] = None  # invalidate cache
            st.session_state["_lb_last_filters"] = None
            st.success(f'✅ Team **"{team_name}"** saved!')
            st.rerun()


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
            mc1, mc2, mc3, mc4 = st.columns([2, 2, 1, 1])
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
                uid = member.get("user_id") or 0
                members[m_idx]["user_id"] = (
                    st.number_input("User ID", value=int(uid), min_value=0, step=1, key=f"_lb_edit_m_id_{m_idx}")
                    or None
                )
            with mc4:
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


def _render_teams_overview() -> None:
    """Show all configured teams with Edit and Delete controls."""
    teams: list[dict] = st.session_state["teams"]
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


def _render_team_result(team_name: str, project_name: str, member_rows: list[dict], totals: dict) -> None:
    """Render analytics for one team: metrics, member table, group breakdown."""
    st.subheader(f"🏅 {team_name}")
    if project_name:
        st.caption(f"Project: {project_name}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Team Score", totals["Team Score"])
    c2.metric("Total Commits", totals["Total Commits"])
    c3.metric("MR Merged", totals["MR Merged"])
    c4.metric("Issues Closed", totals["Issues Closed"])
    c5.metric("Members", len(member_rows))

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
    ]
    df = pd.DataFrame(member_rows)
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], use_container_width=True, hide_index=True)

    group_rows = [
        {"Username": r["Username"], "Groups": r.get("Groups", 0)} for r in member_rows if r.get("Status") == "Success"
    ]
    if group_rows:
        with st.expander("👥 Group Breakdown"):
            st.dataframe(pd.DataFrame(group_rows), use_container_width=True, hide_index=True)

    _render_detailed_contributions(member_rows)

    st.divider()


def _get_daily_activity_counts(mrs, issues, commits) -> dict[str, int]:
    """Aggregates all contributions into a date-based activity map {YYYY-MM-DD: count}."""
    activity_map: dict[str, int] = {}

    def add_to_map(date_str):
        if not date_str:
            return
        # Normalize to YYYY-MM-DD
        try:
            day = date_str.split("T")[0] if "T" in date_str else date_str
            activity_map[day] = activity_map.get(day, 0) + 1
        except Exception:
            pass

    for m in mrs:
        add_to_map(m.get("created_at"))
    for i in issues:
        add_to_map(i.get("created_at"))
    for c in commits:
        add_to_map(c.get("date"))  # Commits already have a "date" field in YYYY-MM-DD

    return activity_map


ICFAI_START_DATE = datetime.date(2026, 1, 5)
RCTS_START_DATE = datetime.date(2026, 1, 27)
ICFAI_USERNAMES = {u.strip().lower() for u in DEFAULT_ICFAI_USERS.splitlines() if u.strip()}
RCTS_USERNAMES = {u.strip().lower() for u in DEFAULT_RCTS_USERS.splitlines() if u.strip()}


def _get_group_start_date(username: str | None) -> datetime.date | None:
    """Return cohort start date for known usernames; otherwise None."""
    uname = (username or "").strip().lower()
    if uname in ICFAI_USERNAMES:
        return ICFAI_START_DATE
    if uname in RCTS_USERNAMES:
        return RCTS_START_DATE
    return None


def _get_contribution_index(activity_map: dict[str, int], username: str | None = None) -> tuple[int, int, float]:
    """
    Returns (active_days, total_days, consistency_pct) for the current leaderboard context.
    If date filter is set, total_days follows that inclusive range.
    Otherwise, total_days is derived from the user's first and last active day.
    """
    active_days = sum(1 for count in activity_map.values() if count > 0)

    total_days = 0
    from_date = st.session_state.get("_lb_from_date")
    to_date = st.session_state.get("_lb_to_date")

    cohort_start = _get_group_start_date(username)
    if cohort_start:
        today = datetime.date.today()
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
    return active_days, total_days, consistency_pct


def _render_activity_heatmap(activity_map: dict[str, int]) -> None:
    """Renders a GitLab-style activity heatmap (364 days)."""
    today = datetime.date.today()
    # Align start to a Monday 52 weeks ago
    start_date = today - datetime.timedelta(days=363)
    while start_date.weekday() != 0:  # 0 is Monday
        start_date -= datetime.timedelta(days=1)

    # Intensity levels (GitLab Blue palette)
    def get_intensity_style(count):
        if count == 0:
            return "rgba(255, 255, 255, 0.05)"
        if count <= 2:
            return "#1e3a5f"
        if count <= 5:
            return "#2b5a91"
        if count <= 10:
            return "#3b7bc4"
        if count <= 20:
            return "#4b9cf7"
        return "#70b1ff"

    weeks_html = []
    current_date = start_date
    months_labels = []
    last_month = None

    # HTML/CSS for the heatmap
    heatmap_styles = """
    <style>
        .heatmap-container {
            background: rgba(17, 19, 24, 0.6);
            border: 1px solid rgba(120, 129, 149, 0.2);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
            overflow-x: auto;
            position: relative;
        }
        .heatmap-grid {
            display: flex;
            gap: 4px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .heatmap-week {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .heatmap-day {
            width: 12px;
            height: 12px;
            border-radius: 2px;
            background: rgba(255, 255, 255, 0.05);
            transition: all 0.2s ease;
        }
        .heatmap-day:hover {
            transform: scale(1.3);
            z-index: 10;
            box-shadow: 0 0 8px rgba(52, 152, 219, 0.5);
            border: 1px solid rgba(255,255,255,0.4);
        }
        .heatmap-today {
            border: 1px solid #70b1ff !important;
        }
        .heatmap-labels-y {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding-right: 10px;
            font-size: 10px;
            color: #888;
            height: 108px; /* 7 * 12 + 6 * 4 */
            padding-top: 2px;
        }
        .heatmap-labels-x {
            display: flex;
            gap: 4px;
            margin-bottom: 5px;
            margin-left: 35px;
            font-size: 10px;
            color: #888;
            height: 15px;
        }
        .month-label { width: 44px; flex-shrink: 0; }
        .heatmap-legend {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            margin-top: 15px;
            gap: 6px;
            font-size: 11px;
            color: #888;
        }
    </style>
    """

    # Generate weeks
    for w in range(53):
        days_in_week = []
        for d in range(7):
            date_str = current_date.isoformat()
            count = activity_map.get(date_str, 0)

            # Month label logic (only show if it's the start of the month)
            if current_date.day <= 7 and current_date.month != last_month:
                months_labels.append(f'<div class="month-label">{current_date.strftime("%b")}</div>')
                last_month = current_date.month
            elif w == 0 and d == 0:
                months_labels.append(f'<div class="month-label">{current_date.strftime("%b")}</div>')

            is_today = "heatmap-today" if current_date == today else ""
            title = f"{current_date.strftime('%b %d, %Y')}: {count} contributions"
            days_in_week.append(
                f'<div class="heatmap-day {is_today}" style="background: {get_intensity_style(count)};" title="{title}"></div>'
            )
            current_date += datetime.timedelta(days=1)

        weeks_html.append(f'<div class="heatmap-week">{"".join(days_in_week)}</div>')

    legend_html = f"""
    <div class="heatmap-legend">
        <span>Less</span>
        <div class="heatmap-day" style="background: {get_intensity_style(0)}"></div>
        <div class="heatmap-day" style="background: {get_intensity_style(2)}"></div>
        <div class="heatmap-day" style="background: {get_intensity_style(5)}"></div>
        <div class="heatmap-day" style="background: {get_intensity_style(10)}"></div>
        <div class="heatmap-day" style="background: {get_intensity_style(21)}"></div>
        <span>More</span>
    </div>
    """

    full_heatmap_html = f"""
    {heatmap_styles}
    <div class="heatmap-container">
        <div class="heatmap-labels-x">{"".join(months_labels)}</div>
        <div class="heatmap-grid">
            <div class="heatmap-labels-y">
                <div>Mon</div><div>Wed</div><div>Fri</div>
            </div>
            {"".join(weeks_html)}
        </div>
        {legend_html}
    </div>
    """
    st.markdown(full_heatmap_html, unsafe_allow_html=True)


def _render_detailed_contributions(member_rows: list[dict]) -> None:
    """Styled expander for detailed contributions (MR titles, Issue titles, Commit messages)."""
    with st.expander("🔍 Detailed Contributions"):
        valid_members = [r for r in member_rows if r.get("Status") == "Success"]
        if not valid_members:
            st.info("No successful member data to show contributions for.")
            return

        DEFAULT_LIMIT = 15
        INCREMENT = 20

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
                            st.plotly_chart(fig, use_container_width=True)
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
            mrs = row.get("mrs_list", [])
            issues = row.get("issues_list", [])
            commits = row.get("commits_list", [])

            st.markdown(f"### 👤 {username}")

            # Render Activity Heatmap
            activity_map = _get_daily_activity_counts(mrs, issues, commits)
            _render_activity_heatmap(activity_map)

            # Contribution Index (as requested: Active Days, Total Days, Consistency %)
            active_days, total_days, consistency_pct = _get_contribution_index(activity_map, username)
            total_contributions = len(mrs) + len(issues) + len(commits)
            collaboration_events = len(mrs) + len(issues)
            collaboration_pct = (collaboration_events / total_contributions) * 100 if total_contributions > 0 else 0.0
            st.markdown("#### 📈 Contribution Index")
            idx_c1, idx_c2, idx_c3, idx_c4 = st.columns(4)
            idx_c1.metric("Active Days", active_days)
            idx_c2.metric("Total Days", total_days)
            idx_c3.metric("Consistency %", f"{consistency_pct:.1f}%")
            idx_c4.metric("Collaboration %", f"{collaboration_pct:.1f}%")

            # Define keys for session state tracking
            mr_limit_key = f"_lb_limit_{username}_mrs"
            issue_limit_key = f"_lb_limit_{username}_issues"
            commit_limit_key = f"_lb_limit_{username}_commits"

            # Helper to generate list HTML
            def get_list_html(items, type_, limit):
                def format_gitlab_date(iso_str):
                    if not iso_str:
                        return None
                    try:
                        dt = dateutil.parser.isoparse(iso_str)
                        return dt.strftime("%b %d, %I:%M %p")
                    except Exception:
                        return None

                html_lines = []
                for item in items[:limit]:
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

                count_suffix = ""
                if len(items) > limit:
                    count_suffix = f"<li style='color:#888; list-style:none; margin-top:5px; font-size:0.9em;'>... and {len(items) - limit} more</li>"

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
                    {count_suffix}
                </ul>
                """

            c1, c2, c3 = st.columns(3)

            # MRs Column
            with c1:
                limit = st.session_state.get(mr_limit_key, DEFAULT_LIMIT)
                st.markdown(
                    f"""
                <div style="background: rgba(255,165,0,0.06); border: 1px solid rgba(255,165,0,0.25); border-radius: 12px; padding: 15px; height: 100%; min-height: 200px;">
                    <h4 style="margin-top:0; color:#ffa500; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(255,165,0,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>📙</span> MRs ({len(mrs)})
                    </h4>
                    {get_list_html(mrs, "mr", limit)}
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Load More / See Less buttons (placed closely below the card)
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                if len(mrs) > limit:
                    if st.button("➕ Load more MRs", key=f"btn_more_mr_{username}", use_container_width=True):
                        st.session_state[mr_limit_key] = limit + INCREMENT
                        st.rerun()
                if limit > DEFAULT_LIMIT:
                    if st.button("➖ See less MRs", key=f"btn_less_mr_{username}", use_container_width=True):
                        st.session_state[mr_limit_key] = DEFAULT_LIMIT
                        st.rerun()

            # Issues Column
            with c2:
                limit = st.session_state.get(issue_limit_key, DEFAULT_LIMIT)
                st.markdown(
                    f"""
                <div style="background: rgba(255,215,0,0.06); border: 1px solid rgba(255,215,0,0.25); border-radius: 12px; padding: 15px; height: 100%; min-height: 200px;">
                    <h4 style="margin-top:0; color:#ffd700; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(255,215,0,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>🎫</span> Issues ({len(issues)})
                    </h4>
                    {get_list_html(issues, "issue", limit)}
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Load More / See Less buttons
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                if len(issues) > limit:
                    if st.button("➕ Load more Issues", key=f"btn_more_iss_{username}", use_container_width=True):
                        st.session_state[issue_limit_key] = limit + INCREMENT
                        st.rerun()
                if limit > DEFAULT_LIMIT:
                    if st.button("➖ See less Issues", key=f"btn_less_iss_{username}", use_container_width=True):
                        st.session_state[issue_limit_key] = DEFAULT_LIMIT
                        st.rerun()

            # Commits Column
            with c3:
                limit = st.session_state.get(commit_limit_key, DEFAULT_LIMIT)
                st.markdown(
                    f"""
                <div style="background: rgba(52,152,219,0.06); border: 1px solid rgba(52,152,219,0.25); border-radius: 12px; padding: 15px; height: 100%; min-height: 200px;">
                    <h4 style="margin-top:0; color:#3498db; display:flex; align-items:center; gap:8px; border-bottom: 1px solid rgba(52,152,219,0.2); padding-bottom: 8px; margin-bottom: 12px;">
                        <span>💻</span> Commits ({len(commits)})
                    </h4>
                    {get_list_html(commits, "commit", limit)}
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # Load More / See Less buttons
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                if len(commits) > limit:
                    if st.button("➕ Load more Commits", key=f"btn_more_com_{username}", use_container_width=True):
                        st.session_state[commit_limit_key] = limit + INCREMENT
                        st.rerun()
                if limit > DEFAULT_LIMIT:
                    if st.button("➖ See less Commits", key=f"btn_less_com_{username}", use_container_width=True):
                        st.session_state[commit_limit_key] = DEFAULT_LIMIT
                        st.rerun()

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
        st.dataframe(df_users[user_perf_cols], use_container_width=True, hide_index=True)
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
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No recent MRs or Issues found for this team.")


# ---------------------------------------------------------------------------
# UI: Overall Leaderboard
# ---------------------------------------------------------------------------


def _render_overall_leaderboard(team_data: dict) -> None:
    """Ranked leaderboard table + bar chart."""
    st.subheader("🏆 Overall Team Leaderboard")

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
        for tn, (meta, _, totals, *_) in team_data.items()
    ]
    df_lb = pd.DataFrame(lb_rows).sort_values("Team Score", ascending=False).reset_index(drop=True)
    df_lb.insert(0, "Rank", range(1, len(df_lb) + 1))
    st.dataframe(df_lb, use_container_width=True, hide_index=True)
    st.divider()


def _build_ranking_rows(team_data: dict) -> list[dict]:
    """Create sorted ranking rows from already aggregated team totals."""
    rows = []
    for team_name, (_, _, totals, *_) in team_data.items():
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
    for team_name, (_, member_rows, _, *_) in team_data.items():
        for row in member_rows:
            if row.get("Status") != "Success":
                continue
            all_members.append(
                {
                    "Username": row.get("Username", "unknown"),
                    "Team Name": team_name,
                    "Total Commits": row.get("Total Commits", 0),
                    "MRs Merged": row.get("MR Merged", 0),
                    "Issues Closed": row.get("Issues Closed", 0),
                    "Score": row.get("Score", 0),
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
            f'<td class="lb-team">{escape(str(row.get("Username", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Team Name", "")))}</td>'
            f'<td class="lb-num">{int(row.get("Total Commits", 0))}</td>'
            f'<td class="lb-num">{int(row.get("MRs Merged", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Issues Closed", 0))}</td>'
            "</tr>"
        )

    html_table = f"""
<div class="lb-rank-wrap">
  <table class="lb-rank-table">
    <thead>
      <tr>
        <th>S.No</th>
        <th>Badge</th>
        <th>Username</th>
        <th>Team Name</th>
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


def _render_ranking_page() -> None:
    """Ranking-only view that reuses previously computed summary rows."""
    st.markdown("### 🏅 Leaderboard Ranking")
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


def render_team_leaderboard(client) -> None:
    """Main render function. Called from app.py with the GitLabClient instance."""
    _init_state()

    if "_lb_cached_results" not in st.session_state:
        st.session_state["_lb_cached_results"] = None
    if "_lb_last_filters" not in st.session_state:
        st.session_state["_lb_last_filters"] = None

    st.subheader("🏆 Team Leaderboard")
    st.markdown(
        "Create and manage teams, then run analytics to compare productivity scores.\n\n"
        "**Score formula:** `Commits × 1 + Merged MRs × 5 + Total MRs × 2 + Issues Closed × 3`"
    )

    # ── Scoped UI Restyling CSS ──────────────────────────────────────────
    # Removed temporarily for debugging
    pass

    # ── Page selector (Button Toggle) ────────────────────────────────────
    st.markdown('<div class="lb-toggle-container">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    current_page = st.session_state.get("_lb_page", "Workspace")

    with col1:
        if st.button(
            "Workspace",
            use_container_width=True,
            key="_btn_workspace",
            type="secondary" if current_page == "Leaderboard Ranking" else "primary",
        ):
            st.session_state["_lb_page"] = "Workspace"
            st.rerun()

    with col2:
        if st.button(
            "Leaderboard Ranking",
            use_container_width=True,
            key="_btn_ranking",
            type="secondary" if current_page == "Workspace" else "primary",
        ):
            st.session_state["_lb_page"] = "Leaderboard Ranking"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    page = st.session_state["_lb_page"]
    st.divider()

    if page == "Leaderboard Ranking":
        _render_ranking_page()
        return

    # ── Section 1: Create Team ────────────────────────────────────────────
    _render_create_team_form()
    st.divider()

    # ── Section 2: Teams Overview (with inline edit) ──────────────────────
    st.markdown("### 📋 Configured Teams")
    _render_teams_overview()
    st.divider()

    # ── Section 3: Analysis ───────────────────────────────────────────────
    teams: list[dict] = st.session_state["teams"]
    if not teams:
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
    run_button_clicked = st.button("▶️ Run Leaderboard Analysis", type="primary", key="_lb_run_btn")
    st.markdown("</div>", unsafe_allow_html=True)
    if run_button_clicked:
        st.session_state["_lb_triggered"] = True

    if not st.session_state.get("_lb_triggered"):
        st.info("Click **▶️ Run Leaderboard Analysis** to fetch data for all teams.")
        return

    # ── Cache key: fingerprint of current teams + date filters ────────────
    current_filters = {
        "teams": [
            {
                "team_name": t["team_name"],
                "project_name": t.get("project_name", ""),
                "members": sorted([m["username"] for m in t.get("members", []) if m.get("username")]),
            }
            for t in teams
        ],
        "since": since_iso,
        "until": until_iso,
    }

    cached_results = st.session_state.get("_lb_cached_results")
    last_filters = st.session_state.get("_lb_last_filters")

    # If cache is valid and filters haven't changed, reuse cached data
    if cached_results is not None and last_filters == current_filters and not run_button_clicked:
        team_data = cached_results
    else:
        # ── Fetch ─────────────────────────────────────────────────────────
        team_data = {}
        progress = st.progress(0, text="Fetching team data…")

        for idx, team in enumerate(teams):
            team_name = team["team_name"]
            usernames = [m["username"] for m in team.get("members", []) if m.get("username")]

            if not usernames:
                team_data[team_name] = (team, [], _aggregate_team_totals([]))
                progress.progress((idx + 1) / len(teams), text=f"Skipped: {team_name}")
                continue

            with st.spinner(f"Fetching **{team_name}** ({len(usernames)} member(s))…"):
                try:
                    results = process_batch_users(
                        client,
                        usernames,
                        since=since_iso,
                        until=until_iso,
                    )
                except Exception as exc:
                    st.warning(f"⚠️ Could not fetch data for **{team_name}**: {exc}")
                    results = []

            member_rows = [_extract_member_row(r) for r in results if r]
            totals = _aggregate_team_totals(member_rows)
            team_data[team_name] = (team, member_rows, totals, results)
            progress.progress((idx + 1) / len(teams), text=f"Done: {team_name}")

        progress.empty()

        if not team_data:
            st.error("No team data could be fetched. Check your GitLab connection.")
            return

        # Store results and filters in cache
        st.session_state["_lb_cached_results"] = team_data
        st.session_state["_lb_last_filters"] = current_filters

        # Cache ranking rows for the Ranking page
        st.session_state["_lb_last_ranking_rows"] = _build_ranking_rows(team_data)
        st.session_state["_lb_last_individual_rows"] = _build_individual_rows(team_data)

    # ── Render results ────────────────────────────────────────────────────
    st.markdown("### 📊 Team Results")

    # Team Selector for detailed view
    view_team = st.selectbox(
        "Select View",
        options=["All Teams"] + list(team_data.keys()),
        index=0,
        key="_lb_selected_view_team_dropdown",
        help="Switch between overview and specific team details.",
    )
    st.divider()

    if view_team == "All Teams":
        for team_name, (meta, member_rows, totals, *_) in team_data.items():
            _render_team_result(team_name, meta.get("project_name", ""), member_rows, totals)
        _render_overall_leaderboard(team_data)
    else:
        # Render specific team analytics
        meta, member_rows, totals, *extra = team_data[view_team]
        raw_results = extra[0] if extra else []
        _render_specific_team_analytics(view_team, meta.get("project_name", ""), member_rows, totals, raw_results)

    # ── Export ────────────────────────────────────────────────────────────
    st.subheader("📥 Export Report")
    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    filename = f"team_leaderboard_{now_ist.strftime('%Y-%m-%d')}.xlsx"
    try:
        st.download_button(
            label="⬇️ Download Full Report (Excel)",
            data=_build_excel_export(team_data),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.error(f"Could not generate Excel export: {exc}")
