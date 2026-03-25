import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from modes import user_profile

@pytest.fixture
def mock_client():
    return MagicMock()

def mock_columns(spec):
    if isinstance(spec, list):
        n = len(spec)
    else:
        n = spec
    return [MagicMock() for _ in range(n)]

def test_render_user_profile_no_info(mock_client):
    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, None)
        mock_err.assert_called_with("User info not provided.")

def test_render_user_profile_success(mock_client):
    info = {
        "id": 1, "username": "john", "name": "John Doe",
        "avatar_url": "http://img", "web_url": "http://web"
    }

    data = {
        "projects": {"personal": [{"name_with_namespace": "p1", "web_url": "u1"}], "contributed": []},
        "commits": [{"project_name": "p1", "message": "m1", "date": "d1", "time": "t1", "slot": "s1"}],
        "commit_stats": {"total": 1, "morning_commits": 1, "afternoon_commits": 0},
        "groups": [{"name": "g1"}],
        "mrs": [{"title": "mr1", "role": "author", "state": "opened", "created_at": "t1"}],
        "mr_stats": {"total": 1, "merged": 0, "opened": 1, "closed": 0},
        "issues": [{"title": "i1", "state": "opened", "created_at": "t1"}],
        "issue_stats": {"total": 1, "opened": 1, "closed": 0}
    }

    with patch("streamlit.columns", side_effect=mock_columns):
        with patch("streamlit.image") as mock_img:
            with patch("streamlit.spinner"):
                with patch("gitlab_utils.batch.process_single_user", return_value={"status": "Success", "data": data}):
                    with patch("streamlit.expander") as mock_exp:
                        mock_exp.return_value.__enter__.return_value = MagicMock()
                        with patch("streamlit.metric"):
                            with patch("streamlit.dataframe"):
                                user_profile.render_user_profile(mock_client, info)
                                mock_img.assert_called_once()

def test_render_user_profile_fetch_error(mock_client):
    info = {"username": "john"}
    with patch("streamlit.columns", side_effect=mock_columns):
        with patch("streamlit.spinner"):
            with patch("gitlab_utils.batch.process_single_user", return_value={"status": "Error", "error": "Fail"}):
                with patch("streamlit.error") as mock_err:
                    user_profile.render_user_profile(mock_client, info)
                    mock_err.assert_called_with("Error fetching data: Fail")

def test_render_user_profile_no_data(mock_client):
    info = {"username": "john"}
    with patch("streamlit.columns", side_effect=mock_columns):
        with patch("streamlit.spinner"):
             with patch("gitlab_utils.batch.process_single_user", return_value=None):
                with patch("streamlit.error") as mock_err:
                    user_profile.render_user_profile(mock_client, info)
                    mock_err.assert_called_with("Error fetching data: Unknown error")

def test_render_user_profile_empty_sections(mock_client):
    info = {"username": "john"}
    data = {
        "projects": {"personal": [], "contributed": [{"name_with_namespace": "c1", "web_url": "cu1"}]},
        "commits": [],
        "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
        "groups": [],
        "mrs": [],
        "mr_stats": {"total": 0, "merged": 0, "opened": 0, "closed": 0},
        "issues": [],
        "issue_stats": {"total": 0, "opened": 0, "closed": 0}
    }
    with patch("streamlit.columns", side_effect=mock_columns):
        with patch("streamlit.spinner"):
            with patch("gitlab_utils.batch.process_single_user", return_value={"status": "Success", "data": data}):
                with patch("streamlit.expander") as mock_exp:
                    mock_exp.return_value.__enter__.return_value = MagicMock()
                    with patch("streamlit.info") as mock_info:
                        user_profile.render_user_profile(mock_client, info)
                        mock_info.assert_called_with("No groups found.")
