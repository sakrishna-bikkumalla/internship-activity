import streamlit as st


def render_user_profile(user_data: dict):
    """
    Renders the user profile UI in Streamlit.
    """

    if not user_data:
        st.warning("No user profile data available.")
        return

    st.subheader("👤 User Profile")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"**Name:** {user_data.get('name', 'N/A')}")
        st.markdown(f"**Username:** {user_data.get('username', 'N/A')}")
        st.markdown(f"**Email:** {user_data.get('email', 'N/A')}")
        st.markdown(f"**State:** {user_data.get('state', 'N/A')}")

    with col2:
        st.markdown(f"**Projects:** {user_data.get('projects', 0)}")
        st.markdown(f"**Open Issues:** {user_data.get('open_issues', 0)}")
        st.markdown(f"**Closed Issues:** {user_data.get('closed_issues', 0)}")
        st.markdown(f"**Open Merge Requests:** {user_data.get('open_mrs', 0)}")
