import os

import streamlit as st
from dotenv import load_dotenv

from gitlab_compliance_checker.infrastructure.gitlab import users
from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient
from gitlab_compliance_checker.ui.batch import render_batch_analytics_ui
from gitlab_compliance_checker.ui.compliance import render_compliance_mode
from gitlab_compliance_checker.ui.leaderboard import render_team_leaderboard
from gitlab_compliance_checker.ui.profile import render_user_profile
from gitlab_compliance_checker.ui.weekly_performance import render_weekly_performance_ui


def cleanup_gitlab_client(client: GitLabClient):
    """Callback to shut down the client's background thread when the resource is evicted."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Cleaning up GitLabClient resource (st.cache_resource eviction)")
    client.close()


@st.cache_resource(on_release=cleanup_gitlab_client)
def get_gitlab_client(url: str, token: str, is_oauth: bool = False):
    """
    Cached GitLab client initialization.
    Ensures only one instance (and one background thread) exists for a set of credentials.
    Streamlit handles persistence across reruns automatically.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Creating NEW GitLabClient resource for {url}")
    return GitLabClient(base_url=url, token=token, is_oauth=is_oauth)


def main():
    # Load environment variables
    load_dotenv()

    # User Identity in Sidebar
    user_info = st.session_state.get("user_info", {})
    if user_info.get("is_logged_in"):
        st.sidebar.header("Account")
        st.sidebar.write(f"Logged in as: **{user_info.get('name')}**")
        if st.sidebar.button("Logout", icon="🚪"):
            st.session_state.clear()
            st.rerun()
        st.sidebar.markdown("---")

    st.title("GitLab Compliance Checker")

    # Sidebar: Config & Mode
    st.sidebar.header("Configuration")

    # 1. GitLab URL (Default to swecha if not in env)
    default_url = os.getenv("GITLAB_URL", "https://code.swecha.org")
    gitlab_url = st.sidebar.text_input("GitLab URL", value=default_url).strip()

    # 2. GitLab Token (Priority: st.session_state -> env -> manual input)
    if user_info.get("is_logged_in") and user_info.get("access_token"):
        gitlab_token = user_info.get("access_token")
        st.sidebar.success("✅ Authenticated via GitLab Login")
    else:
        default_token = os.getenv("GITLAB_TOKEN", "")
        gitlab_token = st.sidebar.text_input("GitLab Token", value=default_token, type="password").strip()

    mode = st.sidebar.radio(
        "Select Mode",
        [
            "Check Project Compliance",
            "User Profile Overview",
            "Team Leaderboard",
            "Batch Analytics",
            "Weekly Performance Tracker",
        ],
    )

    if not gitlab_token:
        st.warning("Please enter a GitLab Token in the sidebar or login with GitLab.")
        st.stop()

    # Initialize Client (Persistent using st.cache_resource)
    is_oauth = True if user_info.get("is_logged_in") else False
    try:
        # Use the obtain token and URL
        client = get_gitlab_client(gitlab_url, gitlab_token, is_oauth=is_oauth)
    except Exception as e:
        st.error(f"Critical Error initializing GitLab client: {e}")
        st.stop()

    # Routing
    if mode == "Check Project Compliance":
        # Compliance mode expects the client wrapper
        render_compliance_mode(client)

    elif mode == "User Profile Overview":
        st.subheader("👤 User Profile Overview")
        user_input = st.text_input("Enter Username", placeholder="username")

        if user_input:
            user_input = user_input.strip()
            with st.spinner(f"Finding user '{user_input}'..."):
                error_msg = None
                try:
                    user_info = users.get_user_by_username(client, user_input)
                except Exception as e:
                    user_info = None
                    error_msg = str(e)

            if error_msg:
                st.error(f"Error: {error_msg}")
            elif user_info:
                render_user_profile(client, user_info)
            else:
                st.error(f"User '{user_input}' not found.")

    elif mode == "Batch Analytics":
        render_batch_analytics_ui(client)

    elif mode == "Team Leaderboard":
        render_team_leaderboard(client)

    elif mode == "Weekly Performance Tracker":
        render_weekly_performance_ui(client)

    else:
        st.error(f"Routing Error: Unknown mode '{mode}' selected.")
