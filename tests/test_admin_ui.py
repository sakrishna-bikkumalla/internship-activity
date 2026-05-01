from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.ui import admin


@pytest.fixture
def mock_roster_service():
    with patch("gitlab_compliance_checker.ui.admin.get_all_batches") as m_batches, \
         patch("gitlab_compliance_checker.ui.admin.add_batch") as m_add_batch, \
         patch("gitlab_compliance_checker.ui.admin.get_all_members_with_teams") as m_members, \
         patch("gitlab_compliance_checker.ui.admin.bulk_import_members") as m_bulk, \
         patch("gitlab_compliance_checker.ui.admin.delete_member") as m_delete, \
         patch("gitlab_compliance_checker.ui.admin.add_or_update_member") as m_add_update, \
         patch("gitlab_compliance_checker.ui.admin.get_session") as m_session:

        m_batches.return_value = [{"id": 1, "name": "Batch 2024", "start_date": "Jan 2024"}]
        m_members.return_value = [
            {
                "id": 1,
                "name": "John Doe",
                "gitlab_username": "jdoe",
                "batch_name": "Batch 2024",
                "team_name": "Team A",
                "gitlab_email": "john@example.com",
                "corpus_username": "jdoc",
                "college_name": "Uni",
                "date_of_joining": "2024-01-01",
            }
        ]
        m_bulk.return_value = (1, [])
        
        yield {
            "batches": m_batches,
            "add_batch": m_add_batch,
            "members": m_members,
            "bulk": m_bulk,
            "delete": m_delete,
            "add_update": m_add_update,
            "session": m_session,
        }


def test_render_admin_management_tabs(mock_roster_service):
    # Just verify it runs without error and renders tabs
    with patch("streamlit.tabs", return_value=[MagicMock() for _ in range(5)]) as m_tabs:
        admin.render_admin_management(MagicMock())
        assert m_tabs.called


def test_render_batch_management_success(mock_roster_service):
    with patch("streamlit.form") as m_form:
        # Mock form submission
        m_form.return_value.__enter__.return_value = MagicMock()
        with patch("streamlit.form_submit_button", return_value=True):
            with patch("streamlit.text_input", return_value="New Batch"):
                with patch("streamlit.date_input") as m_date:
                    m_date.return_value = MagicMock()
                    m_date.return_value.strftime.return_value = "Feb 2024"
                    
                    admin._render_batch_management()
                    
                    mock_roster_service["add_batch"].assert_called_with("New Batch", "Feb 2024")


def test_render_roster_upload_success(mock_roster_service):
    with patch("streamlit.file_uploader") as m_uploader:
        m_file = MagicMock()
        m_file.read.return_value = b"csv_content"
        m_uploader.return_value = m_file
        
        with patch("streamlit.button", return_value=True):
            # We need to mock selectbox for _get_active_batch_selection
            with patch("streamlit.selectbox", return_value="Batch 2024"):
                admin._render_roster_upload()
                mock_roster_service["bulk"].assert_called_with(b"csv_content", 1)


def test_render_roster_table_delete(mock_roster_service):
    with patch("streamlit.dataframe"):
        with patch("streamlit.number_input", return_value=1):
            with patch("streamlit.button", return_value=True):
                admin._render_roster_table()
                mock_roster_service["delete"].assert_called_with(1)


def test_render_member_form_add(mock_roster_service):
    with patch("streamlit.radio", return_value="Add New"):
        with patch("streamlit.selectbox", return_value="Batch 2024"):
            with patch("streamlit.form") as m_form:
                m_form.return_value.__enter__.return_value = MagicMock()
                with patch("streamlit.form_submit_button", return_value=True):
                    with patch("streamlit.text_input", side_effect=["Name", "Team", "user", "email", "c", "g", "ge", "coll"]):
                        admin._render_member_form()
                        assert mock_roster_service["add_update"].called


def test_render_member_form_edit(mock_roster_service):
    with patch("streamlit.radio", return_value="Edit Existing"):
        with patch("streamlit.selectbox", side_effect=["John Doe (@jdoe)", "Batch 2024"]):
            with patch("gitlab_compliance_checker.ui.admin.get_member_by_id") as m_get_id:
                m_get_id.return_value = {
                    "id": 1,
                    "name": "John Doe",
                    "gitlab_username": "jdoe",
                    "team_name": "Team A",
                    "gitlab_email": "jdoe@example.com",
                    "corpus_username": "jdoec",
                    "global_username": "jdoeg",
                    "global_email": "jdoeg@example.com",
                    "college_name": "XYZ",
                }
                with patch("streamlit.form") as m_form:
                    m_form.return_value.__enter__.return_value = MagicMock()
                    with patch("streamlit.form_submit_button", return_value=True):
                        # 8 text fields
                        with patch("streamlit.text_input", return_value="updated"):
                            admin._render_member_form()
                            assert mock_roster_service["add_update"].called
