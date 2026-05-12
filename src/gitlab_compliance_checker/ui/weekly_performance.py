import logging
import time
from datetime import date, timedelta
from typing import Any, cast

import streamlit as st

from gitlab_compliance_checker.infrastructure.corpus.client import CorpusClient
from gitlab_compliance_checker.services.roster_service import (
    get_all_members_with_teams,
    get_member_by_username,
)
from gitlab_compliance_checker.services.weekly_performance.aggregator import (
    _get_ist_hour,
    _parse_ist_date,
    aggregate_intern_data,
)
from gitlab_compliance_checker.services.weekly_performance.models import (
    DailyData,
    InternCSVRow,
    WeeklyActivity,
)

logger = logging.getLogger(__name__)

# Premium UI CSS for status cards
STATUS_CARD_CSS = """
<style>
    .summary-card {
        padding: 12px;
        border-radius: 12px;
        background: #ffffff;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #edf2f7;
        margin-bottom: 12px;
        font-family: 'Inter', sans-serif;
        transition: all 0.3s ease;
    }
    .summary-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.1);
        border-color: #e2e8f0;
    }
    .summary-title {
        font-size: 0.8rem;
        font-weight: 800;
        color: #4a5568;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-bottom: 2px solid #f7fafc;
        padding-bottom: 6px;
        white-space: nowrap;
    }
    .metrics-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
    }
    .metric-item {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        padding: 8px;
        border-radius: 8px;
        background: #f8fafc;
        min-width: 0;
    }
    .metric-label {
        font-size: 0.55rem;
        font-weight: 600;
        color: #718096;
        margin-bottom: 2px;
    }
    .metric-value-container {
        display: flex;
        align-items: center;
        gap: 4px;
    }
    .metric-icon { font-size: 0.9rem; }
    .metric-value {
        font-size: 0.75rem;
        font-weight: 700;
        color: #2d3748;
    }

    /* Specific metric colors */
    .m-mrs .metric-icon { color: #48bb78; }
    .m-issues .metric-icon { color: #f56565; }
    .m-commits .metric-icon { color: #805ad5; }
    .m-time .metric-icon { color: #ed8936; }

    .time-breakdown {
        margin-top: 10px;
        padding-top: 8px;
        border-top: 1px dashed #e2e8f0;
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px;
    }
    .breakdown-item {
        display: flex;
        flex-direction: column;
        font-size: 0.5rem;
    }
    .breakdown-label {
        color: #718096;
        font-weight: 600;
        margin-bottom: 1px;
    }
    .breakdown-value {
        color: #2d3748;
        font-weight: 700;
    }

    .activity-slots-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin: 20px 0;
        background: #ffffff;
        padding: 16px;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.06);
        min-width: 200px;
    }
    .slots-title {
        font-size: 0.65rem;
        font-weight: 800;
        color: #64748b;
        margin-bottom: 5px;
        text-align: center;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .slot-box {
        height: 42px;
        border-radius: 10px;
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(0,0,0,0.08);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .slot-box:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        z-index: 10;
    }
    .slot-label {
        position: absolute;
        right: 12px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 0.9rem;
        font-weight: 950;
        color: rgba(0,0,0,0.8);
        text-shadow: 0 0 4px rgba(255,255,255,1), 0 0 8px rgba(255,255,255,0.5);
        letter-spacing: 0.02em;
        pointer-events: none;
    }

    /* Compact mode for extra hours */
    .slot-box.compact {
        height: 28px;
        border-radius: 6px;
    }
    .slot-box.compact .slot-label {
        font-size: 0.75rem;
    }

    .slot-active {
        background-color: #22c55e;
        box-shadow: inset 0 0 20px rgba(255,255,255,0.2);
    }

    /* Diagonal Hatch for idle slots */
    .slot-idle {
        background: repeating-linear-gradient(
            45deg,
            #ffffff,
            #ffffff 6px,
            #f1f5f9 6px,
            #f1f5f9 12px
        );
    }

    .slot-yellow {
        background: repeating-linear-gradient(
            45deg,
            #fefce8,
            #fefce8 6px,
            #fef08a 6px,
            #fef08a 12px
        );
    }

    .slot-red {
        background: #ef4444;
        box-shadow: inset 0 0 20px rgba(0,0,0,0.1);
    }

    .slot-red-idle {
        background: repeating-linear-gradient(
            45deg,
            #fee2e2,
            #fee2e2 6px,
            #fecaca 6px,
            #fecaca 12px
        );
    }

    .slot-details {
        position: relative;
    }

    .slot-details[open] {
        z-index: 1000;
    }

    .slot-details > summary {
        list-style: none; /* Hide default arrow */
        cursor: pointer;
    }

    .slot-details > summary::-webkit-details-marker {
        display: none;
    }

    .slot-popover {
        position: absolute;
        top: calc(100% + 8px);
        left: 50%;
        transform: translateX(-50%);
        min-width: 16rem;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        box-shadow: 0 12px 28px rgba(0,0,0,0.12);
        border-radius: 10px;
        padding: 8px;
        z-index: 1000;
        max-height: 250px;
        overflow-y: auto;
    }

    /* Popover Caret Arrow */
    .slot-popover::before {
        content: '';
        position: absolute;
        top: -5px;
        left: 50%;
        transform: translateX(-50%) rotate(45deg);
        width: 10px;
        height: 10px;
        background: #ffffff;
        border-top: 1px solid #e2e8f0;
        border-left: 1px solid #e2e8f0;
    }

    .popover-item {
        display: flex;
        align-items: center;
        padding: 8px 10px;
        font-size: 0.75rem;
        color: #4a5568;
        text-decoration: none;
        border-radius: 6px;
        transition: all 0.2s ease;
        margin-bottom: 2px;
    }

    .popover-item:last-child {
        margin-bottom: 0;
    }

    .popover-item:hover {
        background-color: #f7fafc;
        transform: scale(1.01);
        color: #2d3748;
    }

    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.55rem;
        font-weight: 800;
        text-transform: uppercase;
        color: #ffffff;
        margin-right: 8px;
        letter-spacing: 0.05em;
        flex-shrink: 0;
    }

    .item-title {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        font-weight: 500;
        line-height: 1.2;
    }

    .type-mr .badge { background-color: #48bb78; box-shadow: 0 2px 5px rgba(72,187,120,0.3); }
    .type-mr:hover { background-color: #f0fff4; }

    .type-issue .badge { background-color: #f56565; box-shadow: 0 2px 5px rgba(245,101,101,0.3); }
    .type-issue:hover { background-color: #fff5f5; }

    .type-commit .badge { background-color: #805ad5; box-shadow: 0 2px 5px rgba(128,90,213,0.3); }
    .type-commit:hover { background-color: #faf5ff; }

    .type-audio .badge { background-color: #ed8936; box-shadow: 0 2px 5px rgba(237,137,54,0.3); }
    .type-audio:hover { background-color: #fffaf0; }

    /* Horizontal Scroll for Performance Grid */
    [data-testid="stVerticalBlock"]:has(.performance-grid-marker) [data-testid="stHorizontalBlock"] {
        overflow-x: auto !important;
        overflow-y: hidden !important;
        white-space: nowrap !important;
        display: block !important;
        padding-bottom: 2rem !important;
    }

    [data-testid="stVerticalBlock"]:has(.performance-grid-marker) [data-testid="stHorizontalBlock"] > div {
        display: inline-block !important;
        vertical-align: top !important;
        width: 220px !important;
        white-space: normal !important;
        margin-right: 0.5rem !important;
    }
</style>
"""


def _render_summary_card(
    mrs: int,
    issues: int,
    commits: int,
    time_str: str,
    mrs_open_str: str = "0m",
    mrs_merged_str: str = "0m",
    issues_open_str: str = "0m",
    issues_closed_str: str = "0m",
) -> None:
    """Render a unified summary card with 4 metrics and a detailed time breakdown."""
    html = f"""
<div class="summary-card">
    <div class="summary-title">Daily Summary</div>
    <div class="metrics-grid">
        <div class="metric-item m-mrs">
            <div class="metric-label">MRs</div>
            <div class="metric-value-container">
                <span class="metric-icon">🔀</span>
                <span class="metric-value">{mrs}</span>
            </div>
        </div>
        <div class="metric-item m-issues">
            <div class="metric-label">Issues</div>
            <div class="metric-value-container">
                <span class="metric-icon">📝</span>
                <span class="metric-value">{issues}</span>
            </div>
        </div>
        <div class="metric-item m-commits">
            <div class="metric-label">Commits</div>
            <div class="metric-value-container">
                <span class="metric-icon">💻</span>
                <span class="metric-value">{commits}</span>
            </div>
        </div>
        <div class="metric-item m-time">
            <div class="metric-label">Total Time</div>
            <div class="metric-value-container">
                <span class="metric-icon">⌛</span>
                <span class="metric-value">{time_str}</span>
            </div>
        </div>
    </div>

    <div class="time-breakdown">
        <div class="breakdown-item">
            <span class="breakdown-label">MRs Open</span>
            <span class="breakdown-value">{mrs_open_str}</span>
        </div>
        <div class="breakdown-item">
            <span class="breakdown-label">MRs Merged</span>
            <span class="breakdown-value">{mrs_merged_str}</span>
        </div>
        <div class="breakdown-item">
            <span class="breakdown-label">Issues Open</span>
            <span class="breakdown-value">{issues_open_str}</span>
        </div>
        <div class="breakdown-item">
            <span class="breakdown-label">Issues Closed</span>
            <span class="breakdown-value">{issues_closed_str}</span>
        </div>
    </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def _render_activity_slots(
    active_hours: list[int],
    slots: list[int],
    events_by_hour: dict[int, list[Any]] | None = None,
    title: str = "Activity Timeline",
    use_strict_mode: bool = True,
    compact: bool = False,
) -> None:
    """Render vertical activity slots with optional streak-based coloring."""
    is_active = [hour in active_hours for hour in slots]
    num_slots = len(slots)

    # Streak and Global Idle Detection (Only in Strict Mode)
    yellow_slots = [False] * num_slots
    is_total_idle = use_strict_mode and not any(is_active)

    if use_strict_mode and not is_total_idle:
        consecutive_idle = 0
        for i, active in enumerate(is_active):
            if not active:
                consecutive_idle += 1
            else:
                if consecutive_idle >= 4:
                    for j in range(i - consecutive_idle, i):
                        yellow_slots[j] = True
                consecutive_idle = 0
        # Check end of period
        if consecutive_idle >= 4:
            for j in range(len(is_active) - consecutive_idle, len(is_active)):
                yellow_slots[j] = True

    if events_by_hour is None:
        events_by_hour = {}

    svg_html = ""
    for i, hour in enumerate(slots):
        end_hour = (hour + 1) % 24
        slot_label = f"{hour:02d}:00 - {end_hour:02d}:00"
        status_class = "slot-idle"

        if is_total_idle:
            status_class = "slot-red-idle"
        elif is_active[i]:
            status_class = "slot-active"
        elif yellow_slots[i]:
            status_class = "slot-yellow"

        compact_class = "compact" if compact else ""

        hour_events = events_by_hour.get(hour, [])
        if hour_events:
            popover_html = '<div class="slot-popover">'
            for event in hour_events:
                e_type = event.get("type", "").upper()
                type_class = event.get("type", "").lower()
                e_title = event.get("title", "")
                e_url = event.get("url", "#")
                popover_html += f'<a href="{e_url}" target="_blank" class="popover-item type-{type_class}"><span class="badge">{e_type}</span><span class="item-title">{e_title}</span></a>'
            popover_html += "</div>"

            svg_html += f"""
<details class="slot-details">
    <summary class="slot-box {status_class} {compact_class}" title="{slot_label}">
        <div class="slot-label">{slot_label}</div>
    </summary>
    {popover_html}
</details>
"""
        else:
            svg_html += f"""
<div class="slot-box {status_class} {compact_class}" title="{slot_label}">
    <div class="slot-label">{slot_label}</div>
</div>
"""

    html = f"""
<div class="activity-slots-container">
    <div class="slots-title">{title}</div>
    {svg_html}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


def _init_state() -> None:
    if "wp_interns" not in st.session_state:
        st.session_state["wp_interns"] = []

    if "wp_selected_intern" not in st.session_state:
        st.session_state["wp_selected_intern"] = None

    if "wp_corpus_token" not in st.session_state:
        st.session_state["wp_corpus_token"] = None

    if "wp_corpus_client" not in st.session_state:
        st.session_state["wp_corpus_client"] = None

    if "wp_view_mode" not in st.session_state:
        st.session_state["wp_view_mode"] = "7 Day Range"

    if "wp_start_date" not in st.session_state:
        # Default to previous 6 days + today for the 7-day range
        st.session_state["wp_start_date"] = date.today() - timedelta(days=6)

    if "wp_activity_cache" not in st.session_state:
        st.session_state["wp_activity_cache"] = {}


def _get_interns() -> list[InternCSVRow]:
    return cast(list[InternCSVRow], st.session_state.get("wp_interns", []))


def _get_start_date() -> date:
    return cast(date, st.session_state.get("wp_start_date", date.today()))


def _render_corpus_login() -> None:
    with st.sidebar.expander("Corpus Login", expanded=st.session_state.get("wp_corpus_token") is None):
        phone = st.text_input("Phone", key="wp_corpus_phone", placeholder="+1234567890")
        password = st.text_input("Password", key="wp_corpus_password", type="password")
        if st.button("Login to Corpus", key="wp_corpus_login_btn"):
            if not phone or not password:
                st.warning("Phone and password are required.")
            else:
                try:
                    corpus_client = CorpusClient()
                    token = corpus_client.login(phone, password)
                    st.session_state["wp_corpus_token"] = token
                    st.session_state["wp_corpus_client"] = corpus_client
                    st.success("Logged in to Corpus!")
                except Exception as e:
                    st.error(f"Login failed: {e}")


def fetch_team_audio_urls(
    corpus_client: CorpusClient,
    team_members: list[InternCSVRow],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Fetch audio URLs for all team members, grouped by intern and date.

    Returns:
        Dict mapping corpus_uid -> {date_str -> list of audio URLs}
    """
    logger.debug(
        f"[UI] fetch_team_audio_urls called for {len(team_members)} members, dates: {start_date} to {end_date}"
    )
    # Result: { corpus_uid: { date_str: [audio_entries] } }
    audio_data: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for member in team_members:
        corpus_username = member.get("corpus_username")
        if not corpus_username:
            continue

        audio_data[corpus_username] = {}
        logger.debug(f"[UI] Fetching records for member: {member['name']} (corpus_username={corpus_username})")
        try:
            records = corpus_client.fetch_records(corpus_username, start_date, end_date)
            logger.debug(f"[UI] Got {len(records)} records for {member['name']}")

            audio_urls = corpus_client.extract_audio_urls(records)
            logger.debug(f"[UI] Extracted {len(audio_urls)} audio URLs for {member['name']}")

            for url in audio_urls:
                record = next((r for r in records if r.get("file_url") == url), None)
                if not record:
                    continue
                created_at = record.get("created_at", "")
                date_str = _parse_ist_date(created_at) if created_at else None
                if date_str:
                    if date_str not in audio_data[corpus_username]:
                        audio_data[corpus_username][date_str] = []

                    # Store as dict to allow for more metadata if needed
                    audio_entry = {"url": url, "filename": record.get("file_name", "audio"), "created_at": created_at}
                    audio_data[corpus_username][date_str].append(audio_entry)
        except Exception as e:
            logger.error(f"[UI] Failed to fetch records for {member['name']}: {e}")
            st.warning(f"Failed to fetch records for {member['name']}: {e}")

    return audio_data


# Removed _render_csv_upload - functionality moved to Admin Management


def _render_date_selector() -> tuple[Any, str]:
    col_mode, col_date = st.columns([1, 1])
    with col_mode:
        view_mode = st.radio(
            "View Mode",
            options=["7 Day Range", "Single Day", "Custom Range"],
            key="wp_view_mode_radio",
            horizontal=True,
        )
        # Update session state and reset date defaults if mode changed
        if view_mode != st.session_state.get("wp_view_mode"):
            if view_mode == "7 Day Range":
                new_date = date.today() - timedelta(days=6)
                st.session_state["wp_start_date"] = new_date
                st.session_state["wp_date_picker"] = new_date
            elif view_mode == "Single Day":
                new_date = date.today()
                st.session_state["wp_start_date"] = new_date
                st.session_state["wp_date_picker"] = new_date
            st.session_state["wp_view_mode"] = view_mode

    with col_date:
        if view_mode == "Custom Range":
            # Range mode returns a tuple (start, end) or (start,)
            date_range = st.date_input(
                "Select Date Range",
                value=(st.session_state["wp_start_date"], st.session_state["wp_start_date"] + timedelta(days=6)),
                key="wp_date_range_picker",
            )
            return date_range, view_mode
        else:
            start_date = st.date_input(
                "Select Start Date" if view_mode == "7 Day Range" else "Select Date",
                value=st.session_state["wp_start_date"],
                key="wp_date_picker",
            )
            st.session_state["wp_start_date"] = start_date
            return start_date, view_mode


def _render_intern_selector(interns: list[InternCSVRow]) -> Any:
    if not interns:
        st.info("No interns found in the database.")
        return None

    options = ["All Interns"] + [f"{r['name']} (@{r['gitlab_username']})" for r in interns]
    intern_map = {f"{r['name']} (@{r['gitlab_username']})": r for r in interns}

    selected = st.selectbox("Select Intern", options=options, key="wp_intern_select")
    if selected == "All Interns":
        return "ALL"
    return intern_map.get(selected)


def _render_group_member_selector() -> Any:
    group_members = st.session_state.get("fetched_group_members", [])
    if not group_members:
        st.info("No group members found. Please fetch them in the Admin panel.")
        return None

    options = [f"{m['name']} (@{m['username']})" for m in group_members]
    member_map = {
        f"{m['name']} (@{m['username']})": {
            "gitlab_username": m["username"],
            "name": m["name"],
            "corpus_username": None,
            "override_email": m.get("email"),
            "override_username": m.get("username"),
        }
        for m in group_members
    }

    selected = st.selectbox("Select Group Member", options=options, key="wp_group_member_select")
    return member_map.get(selected)


def _render_performance_grid(
    start_date: date,
    activity: WeeklyActivity | None,
    num_days: int = 7,
    show_audio: bool = True,
) -> None:
    with st.container():
        st.markdown('<div class="performance-grid-marker"></div>', unsafe_allow_html=True)
        cols = st.columns(num_days)
        for i, day_col in enumerate(cols):
            day_date = start_date + timedelta(days=i)
            day_key = day_date.isoformat()
            day_data: DailyData = (
                cast(DailyData, activity.daily_data.get(day_key, {})) if activity else cast(DailyData, {})
            )

            gitlab = day_data.get("gitlab", {})
            corpus = day_data.get("corpus", {})

            with day_col:
                st.markdown(f"**{day_date.strftime('%A')}**")
                st.caption(day_date.strftime("%b %d"))

                mrs = gitlab.get("mrs", 0)
                issues = gitlab.get("issues", 0)
                commits = gitlab.get("commits", 0)
                time_spent = gitlab.get("time_spent_seconds", 0)

                def _fmt_h_m(s):
                    if not s:
                        return "0m"
                    h = s // 3600
                    m = (s % 3600) // 60
                    return f"{h}h {m}m" if h > 0 else f"{m}m"

                time_str = _fmt_h_m(time_spent)
                mrs_open_str = _fmt_h_m(gitlab.get("mrs_open_time", 0))
                mrs_merged_str = _fmt_h_m(gitlab.get("mrs_merged_time", 0))
                issues_open_str = _fmt_h_m(gitlab.get("issues_open_time", 0))
                issues_closed_str = _fmt_h_m(gitlab.get("issues_closed_time", 0))

                _render_summary_card(
                    mrs,
                    issues,
                    commits,
                    time_str,
                    mrs_open_str=mrs_open_str,
                    mrs_merged_str=mrs_merged_str,
                    issues_open_str=issues_open_str,
                    issues_closed_str=issues_closed_str,
                )

                # Activity Slots: Office Hours (9 AM - 5 PM)
                active_hours = gitlab.get("active_hours", [])
                events_by_hour = gitlab.get("events_by_hour", {})

                _render_activity_slots(
                    active_hours,
                    slots=[9, 10, 11, 12, 13, 14, 15, 16],
                    events_by_hour=events_by_hour,
                    title="Office Hours (9 am-5 pm)",
                    use_strict_mode=True,
                    compact=False,
                )

                # Activity Slots: Other Hours
                other_slots = [0, 1, 2, 3, 4, 5, 6, 7, 8, 17, 18, 19, 20, 21, 22, 23]
                active_extra_slots = [h for h in other_slots if h in active_hours]
                if active_extra_slots:
                    _render_activity_slots(
                        active_hours,
                        slots=active_extra_slots,
                        events_by_hour=events_by_hour,
                        title="Extra Hours Activity",
                        use_strict_mode=False,
                        compact=True,
                    )

                if show_audio:
                    audio_entries = corpus.get("audio_urls", [])  # Now contains dicts
                    if audio_entries:
                        st.markdown("**🎤 Audio:**")
                        for entry in audio_entries:
                            if isinstance(entry, dict):
                                url = entry.get("url")
                                time_str = ""
                                if entry.get("created_at"):
                                    try:
                                        time_str = f"({entry['created_at'][11:16]})"
                                    except Exception:
                                        pass
                                st.caption(f"{entry.get('filename', 'Audio')} {time_str}")
                            else:
                                url = entry

                            if url:
                                st.audio(url)
                    else:
                        st.caption("No audio")

    if activity and num_days > 1:
        st.divider()
        total_time = activity.total_weekly_time
        total_hours = total_time // 3600
        total_minutes = (total_time % 3600) // 60
        st.metric("Total Time", f"{total_hours}h {total_minutes}m")


def _fetch_all_activity(
    gl_client,
    selected_intern: InternCSVRow,
    start_date: date,
    num_days: int,
    corpus_client: CorpusClient | None,
    pre_fetched_audio: dict[str, list[dict[str, Any]]] | None = None,
) -> WeeklyActivity:
    """Fetch both GitLab and Corpus data with individual caching."""
    # Cache key: (start_date_iso, num_days, gitlab_username)
    cache_key = (start_date.isoformat(), num_days, selected_intern["gitlab_username"])
    if cache_key in st.session_state["wp_activity_cache"]:
        activity = cast(WeeklyActivity, st.session_state["wp_activity_cache"][cache_key])

        if corpus_client and not activity.audio_fetched:
            logger.debug(f"[UI] Cache enrichment required for {selected_intern['name']}")
        else:
            logger.debug(f"[UI] Cache hit for {selected_intern['name']} on {start_date.isoformat()} ({num_days} days)")
            return activity

    # If we are here, either it's a new entry OR we need enrichment
    if cache_key in st.session_state["wp_activity_cache"]:
        activity = st.session_state["wp_activity_cache"][cache_key]
        is_enrichment = True
    else:
        logger.debug(f"[UI] _fetch_all_activity for intern: {selected_intern['name']} ({num_days} days)")
        activity = WeeklyActivity(
            intern_name=selected_intern["name"],
            gitlab_username=selected_intern["gitlab_username"],
            corpus_uid=selected_intern["corpus_username"],
        )
        is_enrichment = False

    # Initialize N days of empty data (Only if not enrichment)
    if not is_enrichment:
        for i in range(num_days):
            day_key = (start_date + timedelta(days=i)).isoformat()
            activity.daily_data[day_key] = {
                "gitlab": {
                    "mrs": 0,
                    "issues": 0,
                    "commits": 0,
                    "time_spent_seconds": 0,
                    "active_hours": [],
                    "events_by_hour": {},
                },
                "corpus": {"audio_urls": []},
            }

    # GitLab Data Fetch (Skip if enrichment)
    if not is_enrichment:
        logger.debug(f"[UI] Fetching GitLab data for {selected_intern['gitlab_username']}")
        with st.spinner(f"Fetching GitLab data for {selected_intern['name']}..."):
            end_date = start_date + timedelta(days=num_days - 1)
            gitlab_activity = aggregate_intern_data(
                gl_client,
                gitlab_username=selected_intern["gitlab_username"],
                corpus_uid=selected_intern["corpus_username"],
                intern_name=selected_intern["name"],
                start_date=start_date,
                end_date=end_date,
                override_email=selected_intern.get("override_email"),
                override_username=selected_intern.get("override_username"),
            )
            for date_str, daily in gitlab_activity.daily_data.items():
                if date_str in activity.daily_data:
                    activity.daily_data[date_str]["gitlab"] = daily.get("gitlab", {})
            activity.total_weekly_time = gitlab_activity.total_weekly_time

    # Corpus Audio Fetch
    if corpus_client:
        if pre_fetched_audio:
            logger.debug(f"[UI] Using pre-fetched audio for: {selected_intern['name']}")
            for date_str, urls in pre_fetched_audio.items():
                if date_str in activity.daily_data:
                    activity.daily_data[date_str]["corpus"]["audio_urls"] = urls
        else:
            logger.debug(f"[UI] Fetching Corpus audio for: {selected_intern['name']}")
            start_date_str: str = start_date.isoformat()
            end_date_str: str = (start_date + timedelta(days=num_days - 1)).isoformat()

            with st.spinner(f"Fetching audio for {selected_intern['name']}..."):
                audio_batch = fetch_team_audio_urls(corpus_client, [selected_intern], start_date_str, end_date_str)
                user_audio = audio_batch.get(selected_intern["corpus_username"], {})
                for date_str, urls in user_audio.items():
                    if date_str in activity.daily_data:
                        activity.daily_data[date_str]["corpus"]["audio_urls"] = urls

                        # Enrich active_hours with Corpus contributions
                        for audio in urls:
                            hr = _get_ist_hour(audio.get("created_at", ""))
                            if hr is not None:
                                current_hours = set(activity.daily_data[date_str]["gitlab"].get("active_hours", []))
                                current_hours.add(hr)
                                activity.daily_data[date_str]["gitlab"]["active_hours"] = sorted(current_hours)

                                events_dict = activity.daily_data[date_str]["gitlab"].setdefault("events_by_hour", {})
                                hr_events = events_dict.setdefault(hr, [])
                                hr_events.append(
                                    {
                                        "type": "audio",
                                        "title": audio.get("filename", "Audio"),
                                        "url": audio.get("url", ""),
                                    }
                                )

        activity.audio_fetched = True

    st.session_state["wp_activity_cache"][cache_key] = activity
    return activity


def render_weekly_performance_ui(gl_client) -> None:
    # Inject custom CSS
    st.markdown(STATUS_CARD_CSS, unsafe_allow_html=True)

    st.subheader("📊 Performance Tracker")

    _init_state()
    _render_corpus_login()

    if not st.session_state.get("wp_corpus_token"):
        st.warning(
            "📻 **Corpus Audio Missing**: Please login with your Corpus credentials in the sidebar to fetch audio contributions."
        )

    role = st.session_state.get("user_role", "intern")
    user_info = st.session_state.get("user_info", {})
    current_username = user_info.get("username") or user_info.get("preferred_username")

    if role == "intern":
        # Fetch the complete intern profile from the database to get the correct corpus_username
        db_member = get_member_by_username(current_username)
        if db_member:
            interns = [db_member]
            st.info(f"Viewing performance for: **{db_member['name']}**")
        else:
            # Fallback to session info if DB lookup fails (though RBAC should prevent this)
            interns = [
                {
                    "team_name": "Standard",
                    "name": str(user_info.get("name", current_username)),
                    "gitlab_username": str(current_username),
                    "gitlab_email": str(user_info.get("email", "")),
                    "corpus_username": str(current_username),
                    "global_username": "",
                    "global_email": "",
                    "date_of_joining": "",
                    "college_name": "",
                }
            ]
            st.info(f"Viewing performance for: **{user_info.get('name')}** (Roster info missing)")
    else:
        interns = get_all_members_with_teams()

    res, view_mode = _render_date_selector()

    if view_mode == "Custom Range":
        if isinstance(res, (tuple, list)) and len(res) == 2:
            start_date, end_date = res
            num_days = (end_date - start_date).days + 1
            if num_days > 45:
                st.warning("⚠️ Ranges longer than 45 days may experience performance issues.")
        else:
            st.info("📅 Please select both start and end dates in the calendar.")
            return
    elif view_mode == "7 Day Range":
        start_date = res
        num_days = 7
    else:  # Single Day
        start_date = res
        num_days = 1

    group_members = st.session_state.get("fetched_group_members", [])
    if not interns and not group_members:
        st.info("No intern data found in the database or fetched from group.")
        if role == "admin":
            st.info(
                "💡 **Admin Tip**: Go to the **Admin: Roster Management** mode to upload a CSV or import group members."
            )
        st.divider()
        st.markdown("**Preview Grid (no data):**")
        _render_performance_grid(start_date, None, num_days=num_days, show_audio=True)
        return

    if role == "intern":
        selected_intern = interns[0] if interns else None
    else:
        if group_members:
            lookup_mode = st.radio(
                "Select Intern From:", options=["Roster", "Group Names"], horizontal=True, key="wp_lookup_mode"
            )
            if lookup_mode == "Roster":
                selected_intern = _render_intern_selector(interns)
            else:
                selected_intern = _render_group_member_selector()
        else:
            selected_intern = _render_intern_selector(interns)

    if selected_intern == "ALL":
        is_all_cached = all(
            (start_date.isoformat(), num_days, intern["gitlab_username"])
            in st.session_state.get("wp_activity_cache", {})
            for intern in interns
        )

        fetch_button_clicked = st.button("🚀 Fetch Team Performance", width="stretch")

        if not fetch_button_clicked and not is_all_cached:
            st.warning("👈 Click **Fetch Team Performance** to load the results for the entire team.")
            return

        st.divider()
        st.info(f"📋 Showing performance for all {len(interns)} interns.")

        corpus_client = st.session_state.get("wp_corpus_client")

        team_audio_data = {}
        if corpus_client:
            with st.spinner("Pre-fetching team audio records..."):
                start_date_str = start_date.isoformat()
                end_date_str = (start_date + timedelta(days=num_days - 1)).isoformat()
                team_audio_data = fetch_team_audio_urls(corpus_client, interns, start_date_str, end_date_str)

        for intern in interns:
            st.markdown(f"### {intern['name']}")
            st.caption(f"GitLab: @{intern['gitlab_username']} | Corpus UID: {intern['corpus_username']}")

            if (start_date.isoformat(), num_days, intern["gitlab_username"]) not in st.session_state.get(
                "wp_activity_cache", {}
            ):
                time.sleep(1)

            intern_audio = team_audio_data.get(intern["corpus_username"], {})
            try:
                activity = _fetch_all_activity(
                    gl_client,
                    intern,
                    start_date,
                    num_days,
                    corpus_client,
                    pre_fetched_audio=intern_audio,
                )
                _render_performance_grid(start_date, activity, num_days=num_days, show_audio=True)
            except Exception as e:
                error_str = str(e)
                if "Rate Limit" in error_str:
                    st.error(
                        f"🛑 **GitLab Rate Limit Reached** for {intern['name']}\n\n{error_str}\n\nPlease wait a few minutes."
                    )
                    # We might want to break here if it's a global rate limit
                    if "429" in error_str:
                        break
                elif "Timeout context manager" in error_str:
                    st.error(
                        f"⚠️ **Async Context Error** for {intern['name']}\n\nThe background event loop encountered a synchronization issue. Please try clicking 'Refresh Data' in the sidebar."
                    )
                else:
                    st.error(f"❌ **Error fetching data** for {intern['name']}\n\n{error_str}")

            st.divider()

    elif isinstance(selected_intern, dict):
        cache_key = (start_date.isoformat(), num_days, selected_intern["gitlab_username"])
        is_cached = cache_key in st.session_state.get("wp_activity_cache", {})

        fetch_button_clicked = st.button(f"🚀 Fetch Performance for {selected_intern['name']}", width="stretch")

        if not fetch_button_clicked and not is_cached:
            st.warning(f"👈 Click **Fetch Performance** to load the results for {selected_intern['name']}.")
            return

        st.divider()
        st.markdown(f"### {selected_intern['name']}")
        st.caption(f"GitLab: @{selected_intern['gitlab_username']} | Corpus UID: {selected_intern['corpus_username']}")

        corpus_client = st.session_state.get("wp_corpus_client")
        try:
            activity = _fetch_all_activity(gl_client, selected_intern, start_date, num_days, corpus_client)
            _render_performance_grid(start_date, activity, num_days=num_days, show_audio=True)
        except Exception as e:
            if "Rate Limit" in str(e):
                st.error(f"🛑 **GitLab Rate Limit Reached**\n\n{e}")
            else:
                st.error(f"Error: {e}")
