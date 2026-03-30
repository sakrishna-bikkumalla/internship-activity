from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from user_profile.profile_ui import render_user_profile


class DummyContextManager:
    def __init__(self):
        self.metric = MagicMock()
        self.markdown = MagicMock()
        self.write = MagicMock()
        self.dataframe = MagicMock()
        self.info = MagicMock()
        self.success = MagicMock()
        self.warning = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.users.get_user_groups.return_value = [
        {"name": "Group A", "full_path": "group/a", "visibility": "public", "web_url": "http://gitlab/group/a"}
    ]
    client.users.get_user_projects.return_value = [
        {
            "name": "My Project",
            "name_with_namespace": "testuser / My Project",
            "web_url": "http://gitlab/project",
            "owner": {"id": 1},
        }
    ]
    client.users.get_user_commits.return_value = [
        {
            "created_at": "2024-03-25T04:00:00Z",
            "project_scope": "Internal",
            "project_name": "Project A",
            "title": "Commit 1",
        }
    ]
    client.users.get_user_issues.return_value = [
        {
            "title": "Issue 1",
            "state": "opened",
            "created_at": "2024-03-25T00:00:00Z",
            "web_url": "http://gitlab/issue/1",
        }
    ]
    client.users.get_user_merge_requests.return_value = [
        {"title": "MR 1", "state": "opened", "created_at": "2024-03-25T00:00:00Z", "web_url": "http://gitlab/mr/1"}
    ]
    return client


@pytest.fixture
def sample_user_info():
    return {
        "id": 1,
        "username": "testuser",
        "name": "Test User",
        "avatar_url": "http://img/avatar.png",
        "web_url": "http://gitlab/testuser",
    }


def make_columns_mock(n):
    return tuple(DummyContextManager() for _ in range(n))


@pytest.fixture
def mock_streamlit():
    with patch("user_profile.profile_ui.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.image = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.dataframe = MagicMock()
        mock_st.info = MagicMock()
        mock_st.warning = MagicMock()
        mock_st.download_button = MagicMock()
        mock_st.columns = MagicMock(side_effect=make_columns_mock)
        yield mock_st


def test_render_user_profile_basic(mock_client, sample_user_info, mock_streamlit):
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.subheader.assert_called()
    mock_streamlit.image.assert_called_once()


def test_render_user_profile_without_avatar(mock_client, mock_streamlit):
    user_info = {"id": 1, "username": "testuser", "name": "Test User", "web_url": "http://gitlab/testuser"}
    render_user_profile(mock_client, user_info)
    mock_streamlit.image.assert_not_called()


def test_render_user_profile_markdown_link(mock_client, sample_user_info, mock_streamlit):
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.markdown.assert_called()


def test_render_user_profile_groups_success(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_groups.return_value = [
        {"name": "Group A", "full_path": "group/a", "visibility": "public", "web_url": "http://gitlab/group/a"}
    ]
    render_user_profile(mock_client, sample_user_info)
    mock_client.users.get_user_groups.assert_called_once_with(1)


def test_render_user_profile_groups_error(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_groups.side_effect = Exception("API Error")
    render_user_profile(mock_client, sample_user_info)
    mock_client.users.get_user_groups.assert_called()


def test_render_user_profile_projects_success(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_projects.return_value = []
    render_user_profile(mock_client, sample_user_info)
    mock_client.users.get_user_projects.assert_called()


def test_render_user_profile_projects_error(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_projects.side_effect = Exception("API Error")
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.warning.assert_called()


def test_render_user_profile_commits_error(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_commits.side_effect = Exception("API Error")
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.warning.assert_called()


def test_render_user_profile_issues_error(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_issues.side_effect = Exception("API Error")
    render_user_profile(mock_client, sample_user_info)
    mock_client.users.get_user_issues.assert_called()


def test_render_user_profile_mrs_error(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_merge_requests.side_effect = Exception("API Error")
    render_user_profile(mock_client, sample_user_info)
    mock_client.users.get_user_merge_requests.assert_called()


def test_render_user_profile_statistics(mock_client, sample_user_info, mock_streamlit):
    render_user_profile(mock_client, sample_user_info)
    assert mock_streamlit.metric.call_count >= 5


def test_render_user_profile_no_projects(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_projects.return_value = []
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.info.assert_called()


def test_render_user_profile_no_groups(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_groups.return_value = []
    render_user_profile(mock_client, sample_user_info)


def test_render_user_profile_no_issues(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_issues.return_value = []
    render_user_profile(mock_client, sample_user_info)


def test_render_user_profile_no_mrs(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_merge_requests.return_value = []
    render_user_profile(mock_client, sample_user_info)


def test_render_user_profile_no_commits(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_commits.return_value = []
    render_user_profile(mock_client, sample_user_info)
    mock_streamlit.info.assert_called()


def test_render_user_profile_contributed_projects(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_projects.return_value = [
        {"name": "Contributed", "web_url": "http://url", "owner": {"id": 999}}
    ]
    render_user_profile(mock_client, sample_user_info)


def test_render_user_profile_commit_statistics(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_commits.return_value = [
        {"created_at": "2024-03-25T04:00:00Z", "project_scope": "Personal", "project_name": "P1", "title": "C1"},
        {"created_at": "2024-03-25T09:00:00Z", "project_scope": "Personal", "project_name": "P1", "title": "C2"},
        {"created_at": "2024-03-25T14:00:00Z", "project_scope": "Contributed", "project_name": "P2", "title": "C3"},
    ]
    render_user_profile(mock_client, sample_user_info)
    assert mock_streamlit.metric.call_count >= 5


def test_render_user_profile_personal_vs_contributed_commits(mock_client, sample_user_info, mock_streamlit):
    mock_client.users.get_user_commits.return_value = [
        {"created_at": "2024-03-25T04:00:00Z", "project_scope": "Personal", "project_name": "P1", "title": "C1"}
    ]
    render_user_profile(mock_client, sample_user_info)
