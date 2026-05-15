from unittest.mock import MagicMock, patch

import pytest
import streamlit as st

from internship_activity_tracker.ui import profile as user_profile


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sample_user_info():
    return {"id": 1, "username": "john", "name": "John Doe", "avatar_url": "http://img", "web_url": "http://web"}


@pytest.fixture
def sample_phase1_data():
    """Data returned by process_single_user_no_commits (no commits fields)."""
    return {
        "projects": {"personal": [{"name_with_namespace": "p1", "web_url": "u1"}], "contributed": []},
        "commits": [],
        "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
        "groups": [{"name": "g1"}],
        "mrs": [{"title": "mr1", "role": "author", "state": "opened", "created_at": "t1", "web_url": "u1"}],
        "mr_stats": {"total": 1, "merged": 0, "opened": 1, "closed": 0},
        "issues": [{"title": "i1", "role": "author", "state": "opened", "created_at": "t1", "web_url": "u1"}],
        "issue_stats": {"total": 1, "opened": 1, "closed": 0},
        "_projs_for_commits": [{"id": 1}],
        "_user_obj_for_commits": {"id": 1, "username": "john"},
        "_since_for_commits": None,
        "_until_for_commits": None,
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
        "_projs_for_commits": [],
        "_user_obj_for_commits": {"id": 1, "username": "john"},
        "_since_for_commits": None,
        "_until_for_commits": None,
    }


def mock_columns(spec):
    if isinstance(spec, list):
        n = len(spec)
    else:
        n = spec
    return [MagicMock() for _ in range(n)]


@pytest.fixture
def mock_streamlit_base():
    session_state = {}
    with (
        patch("streamlit.columns", side_effect=mock_columns),
        patch("streamlit.spinner") as mock_spin,
        patch("streamlit.expander") as mock_exp,
        patch("streamlit.metric"),
        patch("streamlit.dataframe"),
        patch("streamlit.image"),
        patch("streamlit.write"),
        patch("streamlit.markdown"),
        patch("streamlit.subheader"),
        patch("streamlit.button", return_value=False),
        patch.object(st, "session_state", session_state),
    ):
        mock_spin.return_value.__enter__.return_value = MagicMock()
        mock_spin.return_value.__exit__.return_value = False
        mock_exp.return_value.__enter__.return_value = MagicMock()
        mock_exp.return_value.__exit__.return_value = False
        yield {
            "spinner": mock_spin,
            "expander": mock_exp,
            "session_state": session_state,
        }


def test_render_user_profile_no_info(mock_client):
    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, None)
        mock_err.assert_called_with("User info not provided.")


@patch("internship_activity_tracker.infrastructure.gitlab.batch.fetch_commits_for_result")
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_no_commits")
def test_render_user_profile_success(
    mock_no_commits, mock_fetch_commits, mock_client, sample_user_info, sample_phase1_data, mock_streamlit_base
):
    mock_no_commits.return_value = {"status": "Success", "data": sample_phase1_data}
    mock_fetch_commits.return_value = ([], {"total": 0, "morning_commits": 0, "afternoon_commits": 0})

    with patch("streamlit.image") as mock_img:
        user_profile.render_user_profile(mock_client, sample_user_info)
        mock_img.assert_called_once()


@patch("internship_activity_tracker.infrastructure.gitlab.batch.fetch_commits_for_result")
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_no_commits")
def test_render_user_profile_fetch_error(mock_no_commits, mock_fetch_commits, mock_client, mock_streamlit_base):
    mock_no_commits.return_value = {"status": "Error", "error": "Fail"}

    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_err.assert_called_with("Error fetching data: Fail")


@patch("internship_activity_tracker.infrastructure.gitlab.batch.fetch_commits_for_result")
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_no_commits")
def test_render_user_profile_no_data(mock_no_commits, mock_fetch_commits, mock_client, mock_streamlit_base):
    mock_no_commits.return_value = None

    with patch("streamlit.error") as mock_err:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_err.assert_called_with("Error fetching data: Unknown error")


@patch("internship_activity_tracker.infrastructure.gitlab.batch.fetch_commits_for_result")
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_no_commits")
def test_render_user_profile_empty_sections(
    mock_no_commits, mock_fetch_commits, mock_client, sample_empty_data, mock_streamlit_base
):
    mock_no_commits.return_value = {"status": "Success", "data": sample_empty_data}
    mock_fetch_commits.return_value = ([], {"total": 0, "morning_commits": 0, "afternoon_commits": 0})

    with patch("streamlit.info") as mock_info:
        user_profile.render_user_profile(mock_client, {"username": "john"})
        mock_info.assert_called_with("No groups found.")
