import re
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from sqlalchemy.exc import IntegrityError

from ..infrastructure.database import get_session
from ..infrastructure.gitlab.groups import get_group_members
from ..services.roster_service import (
    add_batch,
    add_or_update_member,
    bulk_import_members,
    delete_member,
    get_all_batches,
    get_all_members_with_teams,
    get_member_by_id,
)


def render_admin_management(client):
    st.header("🛠 Admin: Roster Management")
    st.markdown("Manage batches, teams, and interns in the persistent database.")

    tabs = st.tabs(
        ["📅 Manage Batches", "👥 All Members", "📤 Bulk Import", "➕ Add/Edit Member", "🔗 Group URL Import"]
    )

    with tabs[0]:
        _render_batch_management()

    with tabs[1]:
        _render_roster_table()

    with tabs[2]:
        _render_roster_upload()

    with tabs[3]:
        _render_member_form()

    with tabs[4]:
        _render_group_url_import(client)


def _render_group_url_import(client):
    st.subheader("🔗 Group URL Import")
    st.markdown("Fetch members directly from a GitLab group and store them in the temporary session.")

    group_url = st.text_input("GitLab Group URL", placeholder="https://code.swecha.org/corpus")

    col1, col2 = st.columns(2)
    with col1:
        fetch_option = st.selectbox("Fetch Limit", ["All", "Specific Limit"], index=0)
    with col2:
        limit = None
        if fetch_option == "Specific Limit":
            limit = st.number_input("Number of members", min_value=1, value=50, step=10)

    if st.button("🚀 Fetch Group Members", type="primary"):
        if not group_url:
            st.error("Please enter a Group URL.")
            return

        parsed = urlparse(group_url)
        path = parsed.path.strip("/")

        # Handle gitlab.com/groups/ namespace
        if path.startswith("groups/"):
            path = path[len("groups/") :]

        if not path:
            st.error("Could not determine group path from URL.")
            return

        with st.spinner(f"Fetching members for '{path}'..."):
            try:
                members = get_group_members(client, path, limit=limit)

                if members:
                    st.session_state["fetched_group_members"] = members
                    st.success(f"✅ Successfully fetched {len(members)} members!")

                    # Display a preview
                    df = pd.DataFrame(members)
                    st.dataframe(df[["name", "username", "email"]], use_container_width=True, hide_index=True)
                else:
                    st.warning("No members found or group is inaccessible.")
            except Exception as e:
                st.error(f"❌ Error fetching group members: {e}")


def _render_batch_management():
    st.subheader("📅 Manage Batches")

    # List existing batches
    batches = get_all_batches()
    if batches:
        st.write("### Existing Batches")
        batch_df = pd.DataFrame(batches)
        batch_df.columns = ["ID", "Batch Name", "Start Date/Period"]
        st.dataframe(batch_df, use_container_width=True, hide_index=True)
    else:
        st.info("No batches found. Create one below.")

    st.divider()

    # Create new batch form
    st.write("### ➕ Create New Batch")
    with st.form("new_batch_form", clear_on_submit=True):
        b_name = st.text_input("Batch Name", placeholder="e.g. Winter Interns 2024")
        b_date = st.date_input("Start Date", help="Select the starting date for this batch")

        if st.form_submit_button("🚀 Create Batch"):
            if not b_name:
                st.error("Batch Name is required.")
            else:
                try:
                    date_str = b_date.strftime("%b %Y")
                    add_batch(b_name, date_str)
                    st.success(f"✅ Batch '{b_name}' created successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error creating batch: {e}")


def _get_active_batch_selection(key_suffix: str):
    batches = get_all_batches()
    if not batches:
        st.warning("⚠️ No batches created yet. Please create a batch first in the 'Manage Batches' tab.")
        return None

    batch_options = {b["name"]: b["id"] for b in batches}
    selected_name = st.selectbox(
        "🎯 Target Batch",
        options=list(batch_options.keys()),
        help="Select the batch where these members belong",
        key=f"batch_select_{key_suffix}",
    )
    return batch_options[selected_name]


def _render_roster_upload():
    st.subheader("📤 Bulk CSV Import")

    target_batch_id = _get_active_batch_selection("upload")
    if not target_batch_id:
        return

    # Template download
    template_data = "team_name,name,gitlab_username,gitlab_email,corpus_username,global_username,global_email,date_of_joining,college_name\nTeam A,John Doe,jdoe123,john@example.com,jdoe_corpus,jdoe_global,john.global@example.com,2024-01-01,University X"
    st.download_button(
        label="📥 Download CSV Template",
        data=template_data,
        file_name="roster_template.csv",
        mime="text/csv",
        icon="📄",
    )

    uploaded_file = st.file_uploader(
        "Upload Intern CSV", type=["csv"], help="CSV must at least contain 'name' and 'gitlab_username'"
    )

    if uploaded_file is not None:
        if st.button("🚀 Process and Save to Database", type="primary"):
            with st.spinner("Processing CSV..."):
                content = uploaded_file.read()
                count, errors = bulk_import_members(content, target_batch_id)

                if count > 0:
                    st.success("✅ Database upload is successful!")

                if errors:
                    with st.expander(f"❌ Encountered {len(errors)} error(s) during import", expanded=True):
                        for error in errors:
                            st.write(f"- {error}")

                if count > 0 and not errors:
                    st.rerun()
                elif count == 0 and not errors:
                    st.warning("⚠️ No valid records were processed.")


def _render_roster_table():
    st.subheader("Current Roster")
    members = get_all_members_with_teams()
    if not members:
        st.info("No members found in the database.")
        return

    df = pd.DataFrame(members)
    cols = [
        "batch_name",
        "team_name",
        "name",
        "gitlab_username",
        "gitlab_email",
        "corpus_username",
        "college_name",
        "date_of_joining",
        "id",
    ]
    df = df[cols]
    df.columns = [
        "Batch",
        "Team",
        "Name",
        "GitLab User",
        "GitLab Email",
        "Corpus User",
        "College",
        "Date of Joining",
        "ID",
    ]

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Delete section
    st.markdown("### 🗑 Delete Member")
    member_id_to_del = st.number_input("Enter Member ID to delete", min_value=1, step=1, key="del_id_input")
    if st.button("🗑 Delete Member", type="secondary"):
        if delete_member(member_id_to_del):
            st.success(f"✅ Member {member_id_to_del} has been deleted successfully.")
            st.rerun()
        else:
            st.error(f"❌ Member with ID {member_id_to_del} was not found.")


def _render_member_form():
    st.subheader("➕ Add/Edit Member")

    mode = st.radio("Form Mode", ["Add New", "Edit Existing"], horizontal=True, label_visibility="collapsed")

    selected_member_id = None
    initial_data = {
        "name": "",
        "team_name": "",
        "gitlab_username": "",
        "gitlab_email": "",
        "corpus_username": "",
        "global_username": "",
        "global_email": "",
        "college_name": "",
    }

    if mode == "Edit Existing":
        members = get_all_members_with_teams()
        if not members:
            st.warning("No members available to edit.")
            return

        member_options = {f"{m['name']} (@{m['gitlab_username']})": m["id"] for m in members}
        selected_label = st.selectbox("Select Member to Edit", options=["-- Select --"] + list(member_options.keys()))

        if selected_label != "-- Select --":
            selected_member_id = member_options[selected_label]
            member_to_edit = get_member_by_id(selected_member_id)
            if member_to_edit:
                initial_data = member_to_edit
                # team_name needs to be handle specifically if we want to show it
                initial_data["team_name"] = member_to_edit.get("team_name", "")
        else:
            st.info("Select a member above to populate the form.")
            return

    target_batch_id = _get_active_batch_selection("manual")
    if not target_batch_id:
        return

    with st.form("member_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name", value=initial_data["name"], placeholder="John Doe")
            team_name = st.text_input("Team Name", value=initial_data["team_name"], placeholder="Team Alpha")
            gitlab_user = st.text_input("GitLab Username", value=initial_data["gitlab_username"], placeholder="jdoe")
            gitlab_email = st.text_input(
                "GitLab Email", value=initial_data["gitlab_email"], placeholder="jdoe@example.com"
            )
        with col2:
            corpus_user = st.text_input("Corpus Username", value=initial_data["corpus_username"], placeholder="jdoe_c")
            global_user = st.text_input("Global Username", value=initial_data["global_username"], placeholder="jdoe_g")
            global_email = st.text_input(
                "Global Email", value=initial_data["global_email"], placeholder="jdoe_g@example.com"
            )
            college = st.text_input("College Name", value=initial_data["college_name"], placeholder="XYZ University")

        btn_label = "Update Member" if mode == "Edit Existing" else "Save Member"
        submitted = st.form_submit_button(f"💾 {btn_label}", type="primary")

        if submitted:
            # Basic validation
            email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

            if not gitlab_user:
                st.error("GitLab Username is required.")
            elif gitlab_email and not re.match(email_regex, gitlab_email):
                st.error("Invalid GitLab Email format.")
            elif global_email and not re.match(email_regex, global_email):
                st.error("Invalid Global Email format.")
            else:
                try:
                    with get_session() as session:
                        add_or_update_member(
                            session,
                            {
                                "name": name,
                                "team_name": team_name,
                                "gitlab_username": gitlab_user,
                                "gitlab_email": gitlab_email,
                                "corpus_username": corpus_user,
                                "global_username": global_user,
                                "global_email": global_email,
                                "college_name": college,
                            },
                            target_batch_id,
                            member_id=selected_member_id,
                        )
                    if mode == "Edit Existing":
                        st.success("✅ The edit has been successfully done.")
                    else:
                        st.success("✅ The intern has been added to the database successfully.")
                    st.rerun()
                except IntegrityError as e:
                    error_msg = str(e)
                    if "UniqueViolation" in error_msg or "UNIQUE constraint failed" in error_msg:
                        st.error("❌ A member with this GitLab username or email already exists in the database.")
                    else:
                        st.error(f"❌ Database error: {e}")
                except Exception as e:
                    st.error(f"❌ An unexpected error occurred: {e}")
