import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import io
from modes import batch_mode

@pytest.fixture
def mock_client():
    m = MagicMock()
    m.client = MagicMock()
    return m

def test_render_batch_mode_ui_icfai_success(mock_client):
    with patch("streamlit.text_area", side_effect=["user1\nuser2", ""]): # usernames, repo_paths
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                results = [
                    {
                        "username": "user1", "status": "Success",
                        "data": {
                            "projects": {"personal": [1], "contributed": []},
                            "commit_stats": {"total": 10, "morning_commits": 5, "afternoon_commits": 5},
                            "mr_stats": {"total": 2, "merged": 1, "opened": 1, "closed": 0},
                            "issue_stats": {"total": 0, "opened": 0, "closed": 0},
                            "groups": []
                        }
                    }
                ]
                with patch("gitlab_utils.batch.process_batch_users", return_value=results):
                    with patch("streamlit.write"):
                        with patch("streamlit.dataframe"):
                            with patch("streamlit.download_button"):
                                batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

def test_render_batch_mode_ui_rcts_success(mock_client):
    with patch("streamlit.text_area", side_effect=["user1", ""]):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                results = [
                    {
                        "username": "user1", "status": "Success",
                        "data": {
                            "projects": {"personal": [1], "contributed": [2]},
                            "commit_stats": {"total": 5, "morning_commits": 1, "afternoon_commits": 0},
                            "mr_stats": {"total": 2, "merged": 1, "opened": 1, "closed": 0},
                            "issue_stats": {"total": 2, "opened": 1, "closed": 1},
                            "groups": [1]
                        }
                    }
                ]
                with patch("gitlab_utils.batch.process_batch_users", return_value=results):
                    with patch("streamlit.download_button"):
                         batch_mode.render_batch_mode_ui(mock_client, "RCTS")

def test_render_batch_mode_ui_repo_filter(mock_client):
    with patch("streamlit.text_area", side_effect=["user1", "group/repo"]):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                with patch("gitlab_utils.batch.resolve_project_paths", return_value=([123], [])):
                    with patch("gitlab_utils.batch.process_batch_users", return_value=[]):
                         batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

def test_render_batch_mode_ui_repo_resolve_fail(mock_client):
    with patch("streamlit.text_area", side_effect=["user1", "bad/repo"]):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                with patch("gitlab_utils.batch.resolve_project_paths", return_value=([], ["bad/repo"])):
                     with patch("streamlit.error") as mock_err:
                         batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

def test_render_batch_mode_ui_no_usernames(mock_client):
    with patch("streamlit.text_area", return_value=""):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.warning") as mock_warn:
                batch_mode.render_batch_mode_ui(mock_client, "ICFAI")
                mock_warn.assert_called_with("Please enter at least one username.")

def test_render_batch_mode_ui_error_row(mock_client):
    with patch("streamlit.text_area", side_effect=["user1", ""]):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                results = [{"username": "user1", "status": "Error", "error": "Not Found"}]
                with patch("gitlab_utils.batch.process_batch_users", return_value=results):
                    with patch("streamlit.download_button"):
                        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

def test_render_batch_mode_ui_excel_error(mock_client):
    with patch("streamlit.text_area", side_effect=["user1", ""]):
        with patch("streamlit.button", return_value=True):
            with patch("streamlit.spinner"):
                with patch("gitlab_utils.batch.process_batch_users", return_value=[]):
                    with patch("pandas.ExcelWriter", side_effect=Exception("XLSX Error")):
                        with patch("streamlit.error") as mock_err:
                            batch_mode.render_batch_mode_ui(mock_client, "ICFAI")
