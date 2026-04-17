from datetime import date, timedelta

import streamlit as st

from gitlab_compliance_checker.services.weekly_performance.models import (
    InternCSVRow,
    WeeklyActivity,
    parse_intern_csv,
)

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _init_state() -> None:
    if "wp_interns" not in st.session_state:
        st.session_state["wp_interns"]: list[InternCSVRow] = []

    if "wp_selected_intern" not in st.session_state:
        st.session_state["wp_selected_intern"]: str | None = None

    if "wp_corpus_token" not in st.session_state:
        st.session_state["wp_corpus_token"]: str | None = None

    if "wp_week_start" not in st.session_state:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        st.session_state["wp_week_start"] = monday


def _render_corpus_login() -> None:
    with st.sidebar.expander("Corpus Login", expanded=st.session_state.get("wp_corpus_token") is None):
        phone = st.text_input("Phone", key="wp_corpus_phone", placeholder="+1234567890")
        password = st.text_input("Password", key="wp_corpus_password", type="password")
        if st.button("Login to Corpus", key="wp_corpus_login_btn"):
            if not phone or not password:
                st.warning("Phone and password are required.")
            else:
                st.info("Corpus login not yet implemented. Contributor B will complete this.")
                st.session_state["wp_corpus_token"] = "placeholder_token"


def _render_csv_upload() -> list[InternCSVRow]:
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
    return st.session_state["wp_week_start"]


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
        day_data = activity.daily_data.get(day_key, {}) if activity else {}

        gitlab = day_data.get("gitlab", {})
        corpus = day_data.get("corpus", {})

        with day_col:
            st.markdown(f"**{WEEKDAY_NAMES[i]}**  ")
            st.caption(day_date.strftime("%b %d"))

            st.metric("MRs", gitlab.get("mrs", 0))
            st.metric("Issues", gitlab.get("issues", 0))
            st.metric("Commits", gitlab.get("commits", 0))

            time_spent = gitlab.get("time_spent_seconds", 0)
            if time_spent > 0:
                hours = time_spent // 3600
                minutes = (time_spent % 3600) // 60
                st.caption(f"⏱ {hours}h {minutes}m")
            else:
                st.caption("⏱ 0h 0m")

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


def render_weekly_performance_ui() -> None:
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

        placeholder_activity = WeeklyActivity(
            intern_name=selected_intern["full_name"],
            gitlab_username=selected_intern["gitlab_username"],
            corpus_uid=selected_intern["corpus_uid"],
        )
        _render_7day_grid(week_start, placeholder_activity, show_audio=True)
