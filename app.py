import os

import streamlit as st
from dotenv import load_dotenv

from gitlab_utils import users
from gitlab_utils.client import GitLabClient
from modes.batch_analytics import render_batch_analytics_ui
from modes.compliance_mode import render_compliance_mode
from modes.team_leaderboard import render_team_leaderboard
from modes.user_profile import render_user_profile

# --- Page Config ---
st.set_page_config(
    page_title="GitLab Compliance Checker",
    page_icon="🔍",
    layout="wide",
)

# Load environment variables
load_dotenv()


def main():
    st.title("GitLab Compliance Checker")

    # Sidebar: Config & Mode
    st.sidebar.header("Configuration")

    # Credentials (allow override or from env)
    default_url = os.getenv("GITLAB_URL", "https://code.swecha.org")
    default_token = os.getenv("GITLAB_TOKEN", "")

    gitlab_url = st.sidebar.text_input("GitLab URL", value=default_url).strip()
    gitlab_token = st.sidebar.text_input("GitLab Token", value=default_token, type="password").strip()
    ssl_verify = st.sidebar.checkbox("Verify SSL", value=True)

    mode = st.sidebar.radio(
        "Select Mode",
        [
            "Check Project Compliance",
            "User Profile Overview",
            "Team Leaderboard",
            "Batch Analytics",
        ],
    )

    if not gitlab_token:
        st.warning("Please enter a GitLab Token in the sidebar or .env file.")
        st.stop()

    # Initialize Client
    try:
        client = GitLabClient(gitlab_url, gitlab_token, ssl_verify=ssl_verify)
    except Exception as e:
        st.error(f"Critical Error initializing GitLab client: {e}")
        st.stop()

    # Routing
    if mode == "Check Project Compliance":
        # Compliance mode expects the python-gitlab object for now (legacy compatibility)
        render_compliance_mode(client.client)

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

    else:
        st.error(f"Routing Error: Unknown mode '{mode}' selected.")


if __name__ == "__main__":
    main()
