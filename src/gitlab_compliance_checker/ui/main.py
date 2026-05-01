import os

import streamlit as st
from dotenv import load_dotenv

from gitlab_compliance_checker.infrastructure.database import init_db
from gitlab_compliance_checker.infrastructure.gitlab import users
from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient
from gitlab_compliance_checker.services.roster_service import get_all_members_with_teams
from gitlab_compliance_checker.ui.admin import render_admin_management
from gitlab_compliance_checker.ui.batch import render_batch_analytics_ui
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
    try:
        load_dotenv(override=True)
    except TypeError:
        load_dotenv()

    # Initialize Database Tables
    init_db()

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

    # --- Role-Based Filtering ---
    role = st.session_state.get("user_role", "intern")
    full_options = [
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
    elif role == "admin":
        # Admins see everything + the new management page
        options = full_options + ["Admin: Roster Management"]
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

    if mode == "User Profile Overview":
        st.subheader("👤 User Profile Overview")
        if role == "intern":
            # Interns view their own profile - let's add a button as requested
            current_username = user_info.get("username") or user_info.get("preferred_username")
            st.info(f"Ready to fetch profile for: **{user_info.get('name')}**")

            if st.button("🔍 Fetch My Profile", key="profile_fetch_btn_intern"):
                with st.spinner("Fetching your profile..."):
                    try:
                        st.session_state["active_profile_data"] = users.get_user_by_username(client, current_username)
                        st.session_state["active_profile_error"] = None
                    except Exception as e:
                        st.session_state["active_profile_data"] = None
                        st.session_state["active_profile_error"] = str(e)
        else:
            # Admins/Mentors can choose from DB or manual entry
            lookup_options = ["Select from Roster", "Manual Username Input"]
            if st.session_state.get("fetched_group_members"):
                lookup_options.append("Select from Group Names")

            lookup_mode = st.radio("Lookup Method", options=lookup_options, horizontal=True)

            input_username = None
            selected_group_member = None
            if lookup_mode == "Select from Roster":
                members = get_all_members_with_teams()
                if not members:
                    st.warning("No interns found in database.")
                else:
                    user_options = {f"{m['name']} (@{m['gitlab_username']})": m["gitlab_username"] for m in members}
                    selected_label = st.selectbox(
                        "Choose an Intern", options=["-- Select --"] + list(user_options.keys())
                    )
                    if selected_label != "-- Select --":
                        input_username = user_options[selected_label]
            elif lookup_mode == "Select from Group Names":
                group_members = st.session_state.get("fetched_group_members", [])
                member_options = {f"{m['name']} (@{m['username']})": m for m in group_members}
                selected_label = st.selectbox(
                    "Choose a Group Member", options=["-- Select --"] + list(member_options.keys())
                )
                if selected_label != "-- Select --":
                    selected_group_member = member_options[selected_label]
                    input_username = selected_group_member["username"]
            else:
                input_username = st.text_input("Enter GitLab Username", placeholder="username (e.g. jdoe)")

            if st.button("🔍 Fetch Profile", key="profile_fetch_btn_admin"):
                if not input_username or (lookup_mode == "Select from Roster" and input_username == "-- Select --"):
                    st.warning("Please select or enter a username first.")
                else:
                    input_username = input_username.strip()
                    with st.spinner(f"Fetching profile for '{input_username}'..."):
                        try:
                            profile_res = users.get_user_by_username(client, input_username)
                            if profile_res and lookup_mode == "Select from Group Names" and selected_group_member:
                                profile_res["override_email"] = selected_group_member.get("email")
                                profile_res["override_username"] = selected_group_member.get("username")

                            st.session_state["active_profile_data"] = profile_res
                            st.session_state["active_profile_error"] = None
                        except Exception as e:
                            st.session_state["active_profile_data"] = None
                            st.session_state["active_profile_error"] = str(e)

        # Rendering results from session state
        profile_data = st.session_state.get("active_profile_data")
        profile_error = st.session_state.get("active_profile_error")

        if profile_error:
            st.error(f"Error: {profile_error}")
        elif profile_data:
            render_user_profile(client, profile_data)

    elif mode == "Batch Analytics":
        render_batch_analytics_ui(client)

    elif mode == "Team Leaderboard":
        render_team_leaderboard(client)

    elif mode == "Weekly Performance Tracker":
        render_weekly_performance_ui(client)

    elif mode == "Admin: Roster Management":
        render_admin_management(client)

    else:
        st.error(f"Routing Error: Unknown mode '{mode}' selected.")
