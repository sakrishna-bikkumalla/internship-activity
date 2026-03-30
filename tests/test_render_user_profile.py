from unittest.mock import MagicMock, patch

import pytest

from user_profile.render_user_profile import render_user_profile


class DummyColumn:
    def __init__(self):
        self.metric = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestDummyColumn:
    """Tests for DummyColumn to ensure coverage."""

    def test_dummy_column_init(self):
        col = DummyColumn()
        assert col.metric is not None

    def test_dummy_column_context_manager(self):
        col = DummyColumn()
        with col as c:
            assert c is col

    def test_dummy_column_exit(self):
        col = DummyColumn()
        result = col.__exit__(None, None, None)
        assert result is False


@pytest.fixture
def mock_gl():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 42
    user.username = "testuser"
    user.name = "Test User"
    user.web_url = "https://gitlab.com/testuser"
    return user


@pytest.fixture
def mock_streamlit():
    def make_columns(n):
        return tuple(DummyColumn() for _ in range(n))

    with patch("user_profile.render_user_profile.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.text_input = MagicMock(return_value="testuser")
        mock_st.button = MagicMock(return_value=False)
        mock_st.markdown = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.columns = MagicMock(side_effect=make_columns)
        mock_st.dataframe = MagicMock()
        mock_st.success = MagicMock()
        mock_st.error = MagicMock()
        mock_st.info = MagicMock()
        mock_st.warning = MagicMock()
        yield mock_st


def test_render_user_profile_no_username(mock_gl, mock_streamlit):
    mock_streamlit.text_input.return_value = ""
    mock_streamlit.button.return_value = True

    render_user_profile(mock_gl)
    mock_streamlit.warning.assert_called_with("Please enter a username.")


def test_render_user_profile_button_not_clicked(mock_gl, mock_streamlit):
    mock_streamlit.button.return_value = False
    render_user_profile(mock_gl)


@patch("user_profile.render_user_profile.get_user_profile")
@patch("user_profile.render_user_profile.get_user_issues_details")
@patch("user_profile.render_user_profile.get_user_projects_count")
@patch("user_profile.render_user_profile.get_user_groups_count")
@patch("user_profile.render_user_profile.get_user_open_mrs_count")
@patch("user_profile.render_user_profile.get_user_issues_list")
@patch("user_profile.render_user_profile.check_profile_readme")
def test_render_user_profile_success(
    mock_check_readme,
    mock_get_issues_list,
    mock_get_mrs_count,
    mock_get_groups_count,
    mock_get_projects_count,
    mock_get_issues_details,
    mock_get_user_profile,
    mock_gl,
    mock_user,
    mock_streamlit,
):
    mock_get_user_profile.return_value = mock_user
    mock_get_issues_details.return_value = {
        "total": 10,
        "open": 5,
        "closed": 5,
        "today_morning": 1,
        "today_afternoon": 2,
    }
    mock_get_projects_count.return_value = 5
    mock_get_groups_count.return_value = 3
    mock_get_mrs_count.return_value = 2
    mock_get_issues_list.return_value = [{"id": 1, "title": "Test Issue"}]
    mock_check_readme.return_value = {"exists": True, "url": "http://gitlab.com/README"}

    mock_streamlit.button.return_value = True

    render_user_profile(mock_gl)

    mock_get_user_profile.assert_called_with(mock_gl, "testuser")
    assert mock_streamlit.subheader.call_count >= 2


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_user_not_found(mock_get_user_profile, mock_gl, mock_streamlit):
    mock_get_user_profile.return_value = None
    mock_streamlit.button.return_value = True

    render_user_profile(mock_gl)
    mock_streamlit.error.assert_called_with("User not found.")


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_readme_not_found(mock_get_user_profile, mock_gl, mock_user, mock_streamlit):
    mock_get_user_profile.return_value = mock_user
    mock_streamlit.button.return_value = True

    with (
        patch(
            "user_profile.render_user_profile.get_user_issues_details",
            return_value={"total": 0, "open": 0, "closed": 0, "today_morning": 0, "today_afternoon": 0},
        ),
        patch("user_profile.render_user_profile.get_user_projects_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_groups_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_open_mrs_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_issues_list", return_value=[]),
        patch("user_profile.render_user_profile.check_profile_readme", return_value={"exists": False}),
    ):
        render_user_profile(mock_gl)

    mock_streamlit.error.assert_called()


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_readme_exists(mock_get_user_profile, mock_gl, mock_user, mock_streamlit):
    mock_get_user_profile.return_value = mock_user
    mock_streamlit.button.return_value = True

    with (
        patch(
            "user_profile.render_user_profile.get_user_issues_details",
            return_value={"total": 0, "open": 0, "closed": 0, "today_morning": 0, "today_afternoon": 0},
        ),
        patch("user_profile.render_user_profile.get_user_projects_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_groups_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_open_mrs_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_issues_list", return_value=[]),
        patch(
            "user_profile.render_user_profile.check_profile_readme",
            return_value={"exists": True, "url": "http://gitlab.com/README"},
        ),
    ):
        render_user_profile(mock_gl)

    mock_streamlit.success.assert_called()


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_issues_summary(mock_get_user_profile, mock_gl, mock_user, mock_streamlit):
    mock_get_user_profile.return_value = mock_user
    mock_streamlit.button.return_value = True

    with (
        patch(
            "user_profile.render_user_profile.get_user_issues_details",
            return_value={
                "total": 10,
                "open": 5,
                "closed": 5,
                "today_morning": 1,
                "today_afternoon": 2,
            },
        ),
        patch("user_profile.render_user_profile.get_user_projects_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_groups_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_open_mrs_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_issues_list", return_value=[]),
        patch("user_profile.render_user_profile.check_profile_readme", return_value={"exists": True}),
    ):
        render_user_profile(mock_gl)

    assert mock_streamlit.subheader.call_count >= 3


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_detailed_issues(mock_get_user_profile, mock_gl, mock_user, mock_streamlit):
    mock_get_user_profile.return_value = mock_user
    mock_streamlit.button.return_value = True

    issues = [
        {"id": 1, "iid": 10, "title": "Issue 1", "state": "opened"},
        {"id": 2, "iid": 11, "title": "Issue 2", "state": "closed"},
    ]

    with (
        patch(
            "user_profile.render_user_profile.get_user_issues_details",
            return_value={"total": 2, "open": 1, "closed": 1, "today_morning": 0, "today_afternoon": 0},
        ),
        patch("user_profile.render_user_profile.get_user_projects_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_groups_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_open_mrs_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_issues_list", return_value=issues),
        patch("user_profile.render_user_profile.check_profile_readme", return_value={"exists": True}),
    ):
        render_user_profile(mock_gl)

    mock_streamlit.dataframe.assert_called()


@patch("user_profile.render_user_profile.get_user_profile")
def test_render_user_profile_no_issues(mock_get_user_profile, mock_gl, mock_user, mock_streamlit):
    mock_get_user_profile.return_value = mock_user
    mock_streamlit.button.return_value = True

    with (
        patch(
            "user_profile.render_user_profile.get_user_issues_details",
            return_value={"total": 0, "open": 0, "closed": 0, "today_morning": 0, "today_afternoon": 0},
        ),
        patch("user_profile.render_user_profile.get_user_projects_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_groups_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_open_mrs_count", return_value=0),
        patch("user_profile.render_user_profile.get_user_issues_list", return_value=[]),
        patch("user_profile.render_user_profile.check_profile_readme", return_value={"exists": True}),
    ):
        render_user_profile(mock_gl)

    mock_streamlit.info.assert_called()
