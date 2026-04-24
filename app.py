import logging
from urllib.parse import quote

import httpx
import streamlit as st

from gitlab_compliance_checker.ui.main import main

# --- Configuration ---
# Safely fetch auth secrets to avoid KeyError in Production
auth_secrets = st.secrets.get("auth", {})
gitlab_secrets = auth_secrets.get("gitlab", {})

GITLAB_URL = "https://code.swecha.org"
AUTHORIZE_URL = f"{GITLAB_URL}/oauth/authorize"
TOKEN_URL = f"{GITLAB_URL}/oauth/token"
USERINFO_URL = f"{GITLAB_URL}/api/v4/user"

CLIENT_ID = gitlab_secrets.get("client_id")
CLIENT_SECRET = gitlab_secrets.get("client_secret")
REDIRECT_URI = auth_secrets.get("redirect_uri", "http://localhost:8501")

if not CLIENT_ID or not CLIENT_SECRET:
    st.error(
        "❌ **Critical Error**: GitLab Client ID or Secret is missing in st.secrets. Please check your configuration."
    )
    st.stop()


def check_login():
    """Manual OAuth2 Flow for GitLab."""

    # 1. If already logged in, just exit
    if "user_info" in st.session_state:
        return

    # 2. DEBUG: Show what query params we have
    query_params = st.query_params
    if query_params:
        st.write("--- DEBUG: URL Params found ---")
        st.write(query_params)

    # 3. Check if we are returning from GitLab with a 'code'
    if "code" in query_params:
        code = query_params["code"]
        st.info("🔄 Code detected! Exchanging for token...")

        try:
            with httpx.Client() as client:
                data = {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": REDIRECT_URI,
                }
                resp = client.post(TOKEN_URL, data=data)

                if resp.status_code != 200:
                    st.error(f"Failed to exchange token: {resp.text}")
                    st.stop()

                token_data = resp.json()
                access_token = token_data.get("access_token")

                st.info("🔄 Token received! Fetching user profile...")
                headers = {"Authorization": f"Bearer {access_token}"}
                user_resp = client.get(USERINFO_URL, headers=headers)
                user_resp.raise_for_status()
                user_data = user_resp.json()

                user_data["is_logged_in"] = True
                user_data["access_token"] = access_token
                st.session_state["user_info"] = user_data

                st.success(f"✅ Logged in as {user_data.get('username')}")
                st.query_params.clear()
                st.rerun()

        except Exception as e:
            st.error(f"❌ Login failed: {e}")
            st.stop()

    # 4. Not logged in, show the login screen
    st.title("🔒 GitLab Compliance Checker")
    st.write("Please sign in with your Swecha GitLab account to access the compliance dashboard.")

    auth_link = (
        f"{AUTHORIZE_URL}?client_id={CLIENT_ID}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope=openid+profile+email+api"
    )

    st.link_button("🦊 Login with Swecha GitLab", auth_link, use_container_width=True)
    st.stop()


if __name__ == "__main__":
    st.set_page_config(page_title="GitLab Compliance Checker", page_icon="🔍", layout="wide")
    check_login()

    # RBAC Check
    user_info = st.session_state.get("user_info", {})
    username = user_info.get("username") or user_info.get("preferred_username")
    rbac_users = st.secrets.get("rbac", {}).get("users", {})

    if rbac_users and username not in rbac_users:
        st.error(f"⛔ Access Denied: User '{username}' is not authorized.")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()
        st.stop()

    if username in rbac_users:
        st.session_state["user_role"] = rbac_users[username]

    logging.getLogger("gitlab_compliance_checker").setLevel(logging.DEBUG)
    main()
