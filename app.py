import logging

import streamlit as st

from gitlab_compliance_checker.ui.main import main

logging.getLogger("gitlab_compliance_checker").setLevel(logging.DEBUG)

# --- Page Config ---
st.set_page_config(
    page_title="GitLab Compliance Checker",
    page_icon="🔍",
    layout="wide",
)

if __name__ == "__main__":
    main()
