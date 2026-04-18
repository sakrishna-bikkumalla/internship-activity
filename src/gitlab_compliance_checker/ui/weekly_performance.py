import logging
from datetime import date, timedelta
from typing import Any, cast

import streamlit as st

from gitlab_compliance_checker.infrastructure.corpus.client import CorpusClient
from gitlab_compliance_checker.services.weekly_performance.aggregator import aggregate_intern_data
from gitlab_compliance_checker.services.weekly_performance.models import (
    DailyData,
    InternCSVRow,
    WeeklyActivity,
    parse_intern_csv,
)

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Premium UI CSS for status cards
STATUS_CARD_CSS = """
<style>
    .status-card {
        padding: 16px;
        border-radius: 12px;
        border-left: 6px solid;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        transition: all 0.2s ease-in-out;
        display: flex;
        flex-direction: column;
        justify-content: center;
        margin-bottom: 12px;
        font-family: 'Inter', sans-serif;
    }
    .status-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 15px rgba(0,0,0,0.1);
    }
    .status-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 4px;
        letter-spacing: 0.05em;
        opacity: 0.8;
    }
    .status-value {
        font-size: 1.3rem;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .status-icon { font-size: 1.2rem; }

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

    if "wp_week_start" not in st.session_state:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        st.session_state["wp_week_start"] = monday


def _get_interns() -> list[InternCSVRow]:
    return cast(list[InternCSVRow], st.session_state.get("wp_interns", []))


def _get_week_start() -> date:
    return cast(date, st.session_state.get("wp_week_start", date.today()))


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
) -> dict[str, list[str]]:
    """Fetch audio URLs for all team members, grouped by date.

    Returns:
        Dict mapping "YYYY-MM-DD" -> list of audio URLs
    """
    logger.debug(
        f"[UI] fetch_team_audio_urls called for {len(team_members)} members, dates: {start_date} to {end_date}"
    )
    audio_urls_by_date: dict[str, list[str]] = {}

    for member in team_members:
        corpus_uid = member.get("corpus_uid")
        if not corpus_uid:
            continue

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
                date_str = created_at[:10] if isinstance(created_at, str) and created_at else None
                logger.debug(f"[UI] Audio URL: {url}, created_at={created_at}, date_str={date_str}")
                if date_str:
                    if date_str not in audio_urls_by_date:
                        audio_urls_by_date[date_str] = []
                    audio_urls_by_date[date_str].append(url)
        except Exception as e:
            logger.error(f"[UI] Failed to fetch records for {member['full_name']}: {e}")
            st.warning(f"Failed to fetch records for {member['full_name']}: {e}")

    logger.debug(f"[UI] Total audio_urls_by_date: {audio_urls_by_date}")
    return audio_urls_by_date


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


def _render_week_selector() -> date:
    col_prev, col_week, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("← Prev Week", key="wp_prev_week"):
            st.session_state["wp_week_start"] -= timedelta(days=7)
            st.rerun()
    with col_week:
        week_start = st.session_state["wp_week_start"]
        week_end = week_start + timedelta(days=6)
        st.markdown(f"**Week:** {week_start.strftime('%b %d')} – {week_end.strftime('%b %d, %Y')}")
    with col_next:
        if st.button("Next Week →", key="wp_next_week"):
            st.session_state["wp_week_start"] += timedelta(days=7)
            st.rerun()
    return cast(date, st.session_state["wp_week_start"])


def _render_intern_selector(interns: list[InternCSVRow]) -> InternCSVRow | None:
    if not interns:
        st.info("Upload a CSV to see intern data.")
        return None

    intern_options = [f"{r['full_name']} (@{r['gitlab_username']})" for r in interns]
    intern_map = dict(zip(intern_options, interns, strict=False))

    selected = st.selectbox("Select Intern", options=intern_options, key="wp_intern_select")
    return intern_map.get(selected)


def _render_7day_grid(
    week_start: date,
    activity: WeeklyActivity | None,
    show_audio: bool = True,
) -> None:
    cols = st.columns(7)
    for i, day_col in enumerate(cols):
        day_date = week_start + timedelta(days=i)
        day_key = day_date.isoformat()
        day_data: DailyData = cast(DailyData, activity.daily_data.get(day_key, {})) if activity else cast(DailyData, {})

        gitlab = day_data.get("gitlab", {})
        corpus = day_data.get("corpus", {})

        with day_col:
            st.markdown(f"**{WEEKDAY_NAMES[i]}**")
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
                audio_urls = corpus.get("audio_urls", [])
                if audio_urls:
                    st.markdown("**🎤 Standup Audio:**")
                    for url in audio_urls:
                        st.audio(url, format="audio/mp3")
                else:
                    st.caption("No audio")

    if activity:
        st.divider()
        total_time = activity.total_weekly_time
        total_hours = total_time // 3600
        total_minutes = (total_time % 3600) // 60
        st.metric("Total Weekly Time", f"{total_hours}h {total_minutes}m")


def _fetch_all_activity(
    gl_client,
    selected_intern: InternCSVRow,
    week_start: date,
    corpus_client: CorpusClient | None,
) -> WeeklyActivity:
    """Fetch both GitLab and Corpus data (Corpus only for now)."""
    logger.debug(f"[UI] _fetch_all_activity for intern: {selected_intern['full_name']}")
    activity = WeeklyActivity(
        intern_name=selected_intern["full_name"],
        gitlab_username=selected_intern["gitlab_username"],
        corpus_uid=selected_intern["corpus_uid"],
    )

    # Initialize 7 days of empty data
    for i in range(7):
        day_key = (week_start + timedelta(days=i)).isoformat()
        activity.daily_data[day_key] = {
            "gitlab": {"mrs": 0, "issues": 0, "commits": 0, "time_spent_seconds": 0},
            "corpus": {"audio_urls": []},
        }

    # Contributor A: Fetch GitLab data
    logger.debug(f"[UI] Fetching GitLab data for {selected_intern['gitlab_username']}")
    with st.spinner("Fetching GitLab data..."):
        end_date = week_start + timedelta(days=6)
        gitlab_activity = aggregate_intern_data(
            gl_client,
            gitlab_username=selected_intern["gitlab_username"],
            corpus_uid=selected_intern["corpus_uid"],
            intern_name=selected_intern["full_name"],
            start_date=week_start,
            end_date=end_date,
        )
        logger.debug(f"[UI] GitLab activity fetched: {list(gitlab_activity.daily_data.keys())}")
        for date_str, daily in gitlab_activity.daily_data.items():
            if date_str in activity.daily_data:
                activity.daily_data[date_str]["gitlab"] = daily.get("gitlab", {})
        activity.total_weekly_time = gitlab_activity.total_weekly_time

    # Contributor B: Fetch Corpus Audio
    if corpus_client:
        logger.debug(f"[UI] Fetching Corpus audio for: {selected_intern['full_name']}")

        start_date: str = week_start.isoformat()
        end_date_str: str = (week_start + timedelta(days=6)).isoformat()

        with st.spinner("Fetching audio records..."):
            audio_data = fetch_team_audio_urls(corpus_client, [selected_intern], start_date, end_date_str)
            logger.debug(f"[UI] Audio data by date: {audio_data}")

            for date_str, urls in audio_data.items():
                if date_str in activity.daily_data:
                    activity.daily_data[date_str]["corpus"]["audio_urls"] = urls

    return activity


def render_weekly_performance_ui(gl_client) -> None:
    # Inject custom CSS
    st.markdown(STATUS_CARD_CSS, unsafe_allow_html=True)

    st.subheader("📊 Weekly Performance Tracker")

    _init_state()
    _render_corpus_login()

    interns = _render_csv_upload()
    week_start = _render_week_selector()

    if not interns:
        st.info("Upload a CSV file to view intern performance data.")
        st.divider()
        st.markdown("**Preview Grid (no data):**")
        _render_7day_grid(week_start, None, show_audio=True)
        return

    selected_intern = _render_intern_selector(interns)

    if selected_intern:
        st.divider()
        st.markdown(f"### {selected_intern['full_name']}")
        st.caption(f"GitLab: @{selected_intern['gitlab_username']} | Corpus UID: {selected_intern['corpus_uid']}")

        corpus_client = st.session_state.get("wp_corpus_client")
        activity = _fetch_all_activity(gl_client, selected_intern, week_start, corpus_client)
        _render_7day_grid(week_start, activity, show_audio=True)
