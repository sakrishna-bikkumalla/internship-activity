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

    current_username = user_info.get("username") or user_info.get("preferred_username")

    # 2. GitLab Token (Priority: st.session_state -> env -> manual input)
    if user_info.get("is_logged_in") and user_info.get("access_token"):
        gitlab_token = user_info.get("access_token")
        st.sidebar.success("✅ Authenticated via GitLab Login")
    else:
        default_token = os.getenv("GITLAB_TOKEN", "")
        gitlab_token = st.sidebar.text_input("GitLab Token", value=default_token, type="password").strip()

    # --- Role-Based Filtering ---
    role = st.session_state.get("user_role", "intern")
    full_options = [
        "Check Project Compliance",
        "User Profile Overview",
        "Team Leaderboard",
        "Batch Analytics",
        "Weekly Performance Tracker",
    ]

    if role == "intern":
        # Interns see only specific modes
        allowed_options = ["User Profile Overview", "Weekly Performance Tracker"]
        # Filter while maintaining order
        options = [o for o in full_options if o in allowed_options]
    else:
        options = full_options

    mode = st.sidebar.radio(
        "Select Mode",
        options,
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
        if role == "intern":
            # Interns use their own pre-fetched session data
            current_username = user_info.get("username") or user_info.get("preferred_username")
            user_data = user_info
            input_username = current_username
            st.info(f"Viewing profile for: **{user_info.get('name')}**")
            error_msg = None
        else:
            input_username = st.text_input("Enter GitLab Username", placeholder="username (e.g. jdoe)")
            user_data = None
            error_msg = None
            if input_username:
                input_username = input_username.strip()
                with st.spinner(f"Finding user '{input_username}'..."):
                    try:
                        user_data = users.get_user_by_username(client, input_username)
                    except Exception as e:
                        user_data = None
                        error_msg = str(e)

        if error_msg:
            st.error(f"Error: {error_msg}")
        elif user_data:
            render_user_profile(client, user_data)
        elif input_username:
            st.error(f"User '{input_username}' not found.")

    elif mode == "Batch Analytics":
        render_batch_analytics_ui(client)

    elif mode == "Team Leaderboard":
        render_team_leaderboard(client)

    elif mode == "Weekly Performance Tracker":
        render_weekly_performance_ui(client)

    else:
        st.error(f"Routing Error: Unknown mode '{mode}' selected.")
