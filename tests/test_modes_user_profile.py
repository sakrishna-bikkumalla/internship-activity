from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.ui import profile as user_profile


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sample_user_info():
    return {"id": 1, "username": "john", "name": "John Doe", "avatar_url": "http://img", "web_url": "http://web"}


@pytest.fixture
def sample_success_data():
    return {
        "projects": {"personal": [{"name_with_namespace": "p1", "web_url": "u1"}], "contributed": []},
        "commits": [{"project_name": "p1", "message": "m1", "date": "d1", "time": "t1", "slot": "s1"}],
        "commit_stats": {"total": 1, "morning_commits": 1, "afternoon_commits": 0},
        "groups": [{"name": "g1"}],
        "mrs": [{"title": "mr1", "role": "author", "state": "opened", "created_at": "t1"}],
        "mr_stats": {"total": 1, "merged": 0, "opened": 1, "closed": 0},
        "issues": [{"title": "i1", "state": "opened", "created_at": "t1"}],
        "issue_stats": {"total": 1, "opened": 1, "closed": 0},
    }


@pytest.fixture
def sample_empty_data():
    return {
        "projects": {"personal": [], "contributed": [{"name_with_namespace": "c1", "web_url": "cu1"}]},
        "commits": [],
        "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
        "groups": [],
        "mrs": [],
        "mr_stats": {"total": 0, "merged": 0, "opened": 0, "closed": 0},
        "issues": [],
        "issue_stats": {"total": 0, "opened": 0, "closed": 0},
    }


def mock_columns(spec):
    if isinstance(spec, list):
        n = spec[0] if len(spec) == 1 else len(spec)
    else:
        n = spec
    return [MagicMock() for _ in range(n)]


@pytest.fixture
def mock_streamlit_base():
    with (
        patch("streamlit.columns", side_effect=mock_columns),
        patch("streamlit.spinner") as mock_spin,
        patch("streamlit.expander") as mock_exp,
        patch("streamlit.metric"),
        patch("streamlit.dataframe"),
        patch("streamlit.image"),
        patch("streamlit.write"),
    ):
        mock_exp.return_value.__enter__.return_value = MagicMock()
        mock_exp.return_value.__exit__.return_value = False
        yield {
            "spinner": mock_spin,
            "expander": mock_exp,
        }


def test_render_user_profile_no_info(mock_client):
    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, None)
        mock_err.assert_called_with("User info not provided.")


@patch("gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user")
def test_render_user_profile_success(
    mock_process_single_user, mock_client, sample_user_info, sample_success_data, mock_streamlit_base
):
    mock_process_single_user.return_value = {"status": "Success", "data": sample_success_data}

    with patch("streamlit.image") as mock_img:
        user_profile.render_user_profile(mock_client, sample_user_info)
        mock_img.assert_called_once()


@patch("gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user")
def test_render_user_profile_fetch_error(mock_process_single_user, mock_client, mock_streamlit_base):
    mock_process_single_user.return_value = {"status": "Error", "error": "Fail"}

    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_err.assert_called_with("Error fetching data: Fail")


@patch("gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user")
def test_render_user_profile_no_data(mock_process_single_user, mock_client, mock_streamlit_base):
    mock_process_single_user.return_value = None

    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_err.assert_called_with("Error fetching data: Unknown error")


@patch("gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user")
def test_render_user_profile_empty_sections(
    mock_process_single_user, mock_client, sample_empty_data, mock_streamlit_base
):
    mock_process_single_user.return_value = {"status": "Success", "data": sample_empty_data}

    with patch("streamlit.info") as mock_info:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_info.assert_called_with("No groups found.")
