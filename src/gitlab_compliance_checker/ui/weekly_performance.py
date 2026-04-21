import logging
import time
from datetime import date, timedelta
from typing import Any, cast

import streamlit as st

from gitlab_compliance_checker.infrastructure.corpus.client import CorpusClient
from gitlab_compliance_checker.services.weekly_performance.aggregator import (
    _parse_ist_date,
    aggregate_intern_data,
)
from gitlab_compliance_checker.services.weekly_performance.models import (
    DailyData,
    InternCSVRow,
    WeeklyActivity,
    parse_intern_csv,
)

logger = logging.getLogger(__name__)

# Premium UI CSS for status cards
STATUS_CARD_CSS = """
<style>
    .status-card {
        padding: 10px 4px;
        border-radius: 10px;
        border-left: 4px solid;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: all 0.2s ease-in-out;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        margin-bottom: 8px;
        font-family: 'Inter', sans-serif;
        overflow: hidden;
    }
    .status-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    .status-label {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 4px;
        letter-spacing: 0.03em;
        opacity: 0.9;
        white-space: nowrap;
    }
    .status-value {
        font-size: 1.0rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        width: 100%;
    }
    .status-icon { font-size: 1.0rem; }

    .block-mrs { background-color: #E8F5E9; border-left-color: #4CAF50; color: #1B5E20; }
    .block-issues { background-color: #FCE4EC; border-left-color: #E91E63; color: #880E4F; }
    .block-commits { background-color: #F3E5F5; border-left-color: #9C27B0; color: #4A148C; }
    .block-time { background-color: #FFF3E0; border-left-color: #FF9800; color: #E65100; }
</style>
"""


def _render_status_block(label: str, value: Any, type_class: str, icon: str) -> None:
    """Render a styled status block with dynamic height."""
    # Scale height based on value to create a bar-chart-like effect
    base_height = 70
    extra_height = 0

    if isinstance(value, int):
        extra_height = min(value * 8, 100)
    elif isinstance(value, str) and "h" in value:
        try:
            hours = int(value.split("h")[0])
            extra_height = min(hours * 12, 120)
        except Exception:
            pass

    total_height = base_height + extra_height

    html = f"""
    <div class="status-card {type_class}" style="height: {total_height}px;">
        <div class="status-label">{label}</div>
        <div class="status-value">
            <span class="status-icon">{icon}</span>
            <span>{value}</span>
        </div>
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
        st.session_state["wp_start_date"] = date.today()

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
        corpus_uid = member.get("corpus_uid")
        if not corpus_uid:
            continue

        audio_data[corpus_uid] = {}
        logger.debug(f"[UI] Fetching records for member: {member['full_name']} (corpus_uid={corpus_uid})")
        try:
            records = corpus_client.fetch_records(corpus_uid, start_date, end_date)
            logger.debug(f"[UI] Got {len(records)} records for {member['full_name']}")

            audio_urls = corpus_client.extract_audio_urls(records)
            logger.debug(f"[UI] Extracted {len(audio_urls)} audio URLs for {member['full_name']}")

            for url in audio_urls:
                record = next((r for r in records if r.get("file_url") == url), None)
                if not record:
                    continue
                created_at = record.get("created_at", "")
                date_str = _parse_ist_date(created_at) if created_at else None
                if date_str:
                    if date_str not in audio_data[corpus_uid]:
                        audio_data[corpus_uid][date_str] = []

                    # Store as dict to allow for more metadata if needed
                    audio_entry = {"url": url, "filename": record.get("file_name", "audio"), "created_at": created_at}
                    audio_data[corpus_uid][date_str].append(audio_entry)
        except Exception as e:
            logger.error(f"[UI] Failed to fetch records for {member['full_name']}: {e}")
            st.warning(f"Failed to fetch records for {member['full_name']}: {e}")

    return audio_data


def _render_csv_upload() -> list[InternCSVRow]:
    with st.expander("📋 CSV Format Guide", expanded=False):
        st.markdown(
            "**Expected CSV Structure:**\n\n"
            "| Column | Description | Example |\n"
            "|--------|-------------|---------|\n"
            "| `Team Name` | Name of the team | `Backend` |\n"
            "| `Full Name` | Intern's full name | `John Doe` |\n"
            "| `GitLab Username` | GitLab username (used for MRs, issues, commits, timelogs) | `johndoe` |\n"
            "| `Corpus UID` | Corpus username or user ID (used for standup audio - separate from GitLab) | `johndoe` |\n\n"
            "**Note:** GitLab Username and Corpus UID are separate systems. "
            "GitLab tracks code activity; Corpus tracks standup audio.\n\n"
            "**Sample CSV:**\n\n"
            "```csv\n"
            "Team Name,Full Name,GitLab Username,Corpus UID\n"
            "Backend,John Doe,johndoe,johndoe\n"
            "Frontend,Jane Smith,janesmith,janesmith\n"
            "```"
        )

    uploaded = st.file_uploader(
        "Upload Interns CSV",
        type=["csv"],
        key="wp_csv_uploader",
        help="CSV must have columns: Team Name, Full Name, GitLab Username, Corpus UID",
    )

    if uploaded is None:
        return []

    try:
        rows = parse_intern_csv(uploaded.read())
        if not rows:
            st.warning("CSV file is empty.")
            return []
        st.session_state["wp_interns"] = rows
        return rows
    except Exception as e:
        st.error(f"Failed to parse CSV: {e}")
        return []


def _render_date_selector() -> tuple[Any, str]:
    col_mode, col_date = st.columns([1, 1])
    with col_mode:
        view_mode = st.radio(
            "View Mode",
            options=["7 Day Range", "Single Day", "Custom Range"],
            key="wp_view_mode_radio",
            horizontal=True,
        )
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
        st.info("Upload a CSV to see intern data.")
        return None

    options = ["All Interns"] + [f"{r['full_name']} (@{r['gitlab_username']})" for r in interns]
    intern_map = {f"{r['full_name']} (@{r['gitlab_username']})": r for r in interns}

    selected = st.selectbox("Select Intern", options=options, key="wp_intern_select")
    if selected == "All Interns":
        return "ALL"
    return intern_map.get(selected)


def _render_performance_grid(
    start_date: date,
    activity: WeeklyActivity | None,
    num_days: int = 7,
    show_audio: bool = True,
) -> None:
    cols = st.columns(num_days)
    for i, day_col in enumerate(cols):
        day_date = start_date + timedelta(days=i)
        day_key = day_date.isoformat()
        day_data: DailyData = cast(DailyData, activity.daily_data.get(day_key, {})) if activity else cast(DailyData, {})

        gitlab = day_data.get("gitlab", {})
        corpus = day_data.get("corpus", {})

        with day_col:
            st.markdown(f"**{day_date.strftime('%A')}**")
            st.caption(day_date.strftime("%b %d"))

            _render_status_block("MRs", gitlab.get("mrs", 0), "block-mrs", "🔀")
            _render_status_block("Issues", gitlab.get("issues", 0), "block-issues", "📝")
            _render_status_block("Commits", gitlab.get("commits", 0), "block-commits", "💻")

            time_spent = gitlab.get("time_spent_seconds", 0)
            time_str = "0h 0m"
            if time_spent > 0:
                hours = time_spent // 3600
                minutes = (time_spent % 3600) // 60
                time_str = f"{hours}h {minutes}m"

            _render_status_block("Time Spent", time_str, "block-time", "⌛")

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
            logger.debug(f"[UI] Cache enrichment required for {selected_intern['full_name']}")
        else:
            logger.debug(
                f"[UI] Cache hit for {selected_intern['full_name']} on {start_date.isoformat()} ({num_days} days)"
            )
            return activity

    # If we are here, either it's a new entry OR we need enrichment
    if cache_key in st.session_state["wp_activity_cache"]:
        activity = st.session_state["wp_activity_cache"][cache_key]
        is_enrichment = True
    else:
        logger.debug(f"[UI] _fetch_all_activity for intern: {selected_intern['full_name']} ({num_days} days)")
        activity = WeeklyActivity(
            intern_name=selected_intern["full_name"],
            gitlab_username=selected_intern["gitlab_username"],
            corpus_uid=selected_intern["corpus_uid"],
        )
        is_enrichment = False

    # Initialize N days of empty data (Only if not enrichment)
    if not is_enrichment:
        for i in range(num_days):
            day_key = (start_date + timedelta(days=i)).isoformat()
            activity.daily_data[day_key] = {
                "gitlab": {"mrs": 0, "issues": 0, "commits": 0, "time_spent_seconds": 0},
                "corpus": {"audio_urls": []},
            }

    # GitLab Data Fetch (Skip if enrichment)
    if not is_enrichment:
        logger.debug(f"[UI] Fetching GitLab data for {selected_intern['gitlab_username']}")
        with st.spinner(f"Fetching GitLab data for {selected_intern['full_name']}..."):
            end_date = start_date + timedelta(days=num_days - 1)
            gitlab_activity = aggregate_intern_data(
                gl_client,
                gitlab_username=selected_intern["gitlab_username"],
                corpus_uid=selected_intern["corpus_uid"],
                intern_name=selected_intern["full_name"],
                start_date=start_date,
                end_date=end_date,
            )
            for date_str, daily in gitlab_activity.daily_data.items():
                if date_str in activity.daily_data:
                    activity.daily_data[date_str]["gitlab"] = daily.get("gitlab", {})
            activity.total_weekly_time = gitlab_activity.total_weekly_time

    # Corpus Audio Fetch
    if corpus_client:
        if pre_fetched_audio:
            logger.debug(f"[UI] Using pre-fetched audio for: {selected_intern['full_name']}")
            for date_str, urls in pre_fetched_audio.items():
                if date_str in activity.daily_data:
                    activity.daily_data[date_str]["corpus"]["audio_urls"] = urls
        else:
            logger.debug(f"[UI] Fetching Corpus audio for: {selected_intern['full_name']}")
            start_date_str: str = start_date.isoformat()
            end_date_str: str = (start_date + timedelta(days=num_days - 1)).isoformat()

            with st.spinner(f"Fetching audio for {selected_intern['full_name']}..."):
                audio_batch = fetch_team_audio_urls(corpus_client, [selected_intern], start_date_str, end_date_str)
                user_audio = audio_batch.get(selected_intern["corpus_uid"], {})
                for date_str, urls in user_audio.items():
                    if date_str in activity.daily_data:
                        activity.daily_data[date_str]["corpus"]["audio_urls"] = urls

        activity.audio_fetched = True

    st.session_state["wp_activity_cache"][cache_key] = activity
    return activity


def render_weekly_performance_ui(gl_client) -> None:
    # Inject custom CSS
    st.markdown(STATUS_CARD_CSS, unsafe_allow_html=True)

    st.subheader("📊 Performance Tracker")

    _init_state()
    _render_corpus_login()

    with st.sidebar:
        st.divider()
        if st.button("🔄 Refresh Data", help="Clear cache and re-fetch from GitLab"):
            st.session_state["wp_activity_cache"] = {}
            st.rerun()

    interns = _render_csv_upload()
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

    if not interns:
        st.info("Upload a CSV file to view intern performance data.")
        st.divider()
        st.markdown("**Preview Grid (no data):**")
        _render_performance_grid(start_date, None, num_days=num_days, show_audio=True)
        return

    selected_intern = _render_intern_selector(interns)

    if selected_intern == "ALL":
        is_all_cached = all(
            (start_date.isoformat(), num_days, intern["gitlab_username"])
            in st.session_state.get("wp_activity_cache", {})
            for intern in interns
        )

        fetch_button_clicked = st.button("🚀 Fetch Team Performance", use_container_width=True)

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
            st.markdown(f"### {intern['full_name']}")
            st.caption(f"GitLab: @{intern['gitlab_username']} | Corpus UID: {intern['corpus_uid']}")

            if (start_date.isoformat(), num_days, intern["gitlab_username"]) not in st.session_state.get(
                "wp_activity_cache", {}
            ):
                time.sleep(1)

            intern_audio = team_audio_data.get(intern["corpus_uid"], {})
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
                        f"🛑 **GitLab Rate Limit Reached** for {intern['full_name']}\n\n{error_str}\n\nPlease wait a few minutes."
                    )
                    # We might want to break here if it's a global rate limit
                    if "429" in error_str:
                        break
                elif "Timeout context manager" in error_str:
                    st.error(
                        f"⚠️ **Async Context Error** for {intern['full_name']}\n\nThe background event loop encountered a synchronization issue. Please try clicking 'Refresh Data' in the sidebar."
                    )
                else:
                    st.error(f"❌ **Error fetching data** for {intern['full_name']}\n\n{error_str}")

            st.divider()

    elif selected_intern:
        cache_key = (start_date.isoformat(), num_days, selected_intern["gitlab_username"])
        is_cached = cache_key in st.session_state.get("wp_activity_cache", {})

        fetch_button_clicked = st.button(
            f"🚀 Fetch Performance for {selected_intern['full_name']}", use_container_width=True
        )

        if not fetch_button_clicked and not is_cached:
            st.warning(f"👈 Click **Fetch Performance** to load the results for {selected_intern['full_name']}.")
            return

        st.divider()
        st.markdown(f"### {selected_intern['full_name']}")
        st.caption(f"GitLab: @{selected_intern['gitlab_username']} | Corpus UID: {selected_intern['corpus_uid']}")

        corpus_client = st.session_state.get("wp_corpus_client")
        try:
            activity = _fetch_all_activity(gl_client, selected_intern, start_date, num_days, corpus_client)
            _render_performance_grid(start_date, activity, num_days=num_days, show_audio=True)
        except Exception as e:
            if "Rate Limit" in str(e):
                st.error(f"🛑 **GitLab Rate Limit Reached**\n\n{e}")
            else:
                st.error(f"Error: {e}")
