from unittest.mock import MagicMock, patch

import pytest

from modes.bad_issue import (
    cached_batch_evaluate_issues,
    cached_single_user_issues,
    render_bad_issue_batch_ui,
)


class DummyColumn:
    def __init__(self):
        self.metric = MagicMock()
        self.text_input = MagicMock(return_value="")
        self.button = MagicMock(return_value=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DummyExpander:
    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DummySpinner:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.client = MagicMock()
    return client


@pytest.fixture
def mock_streamlit():
    def make_columns(n):
        if isinstance(n, list):
            return tuple(DummyColumn() for _ in n)
        return tuple(DummyColumn() for _ in range(n))

    with patch("modes.bad_issue.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.expander = MagicMock(return_value=DummyExpander())
        mock_st.button = MagicMock(return_value=False)
        mock_st.code = MagicMock()
        mock_st.spinner = MagicMock(return_value=DummySpinner())
        mock_st.error = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.caption = MagicMock()
        mock_st.dataframe = MagicMock()
        mock_st.download_button = MagicMock()
        mock_st.columns = MagicMock(side_effect=make_columns)
        mock_st.text_input = MagicMock(return_value="")
        mock_st.warning = MagicMock()
        mock_st.success = MagicMock()
        yield mock_st


@pytest.fixture
def sample_issue_rows():
    return [
        {
            "Username": "user1",
            "Total Assigned": 15,
            "Opened Issues": 5,
            "Closed Issues": 10,
            "No Desc": 2,
            "No Labels": 3,
            "No Milestone": 4,
            "No Time Spent": 5,
            "Long Open Time (>2 days)": 6,
            "No Semantic Title": 7,
        },
        {
            "Username": "user2",
            "Total Assigned": 8,
            "Opened Issues": 3,
            "Closed Issues": 5,
            "No Desc": 1,
            "No Labels": 2,
            "No Milestone": 1,
            "No Time Spent": 2,
            "Long Open Time (>2 days)": 3,
            "No Semantic Title": 4,
        },
    ]


class TestCachedFunctions:
    """Tests for cached functions."""

    @patch("modes.bad_issue.st.cache_data", lambda ttl=None: lambda f: f)
    def test_cached_batch_evaluate_issues(self):
        """Test cached_batch_evaluate_issues calls batch_evaluate_issues."""
        mock_client = MagicMock()
        mock_client.batch_evaluate_issues.return_value = [{"username": "test", "Closed Issues": 5}]

        result = cached_batch_evaluate_issues(mock_client, ("user1", "user2"))

        assert len(result) == 1
        mock_client.batch_evaluate_issues.assert_called_once_with(["user1", "user2"], issue_scope="assignee")

    @patch("modes.bad_issue.st.cache_data", lambda ttl=None: lambda f: f)
    def test_cached_single_user_issues(self):
        """Test cached_single_user_issues calls batch_evaluate_issues with single user."""
        mock_client = MagicMock()
        mock_client.batch_evaluate_issues.return_value = [{"username": "test", "Closed Issues": 3}]

        cached_single_user_issues(mock_client, "testuser")

        mock_client.batch_evaluate_issues.assert_called_once_with(["testuser"], issue_scope="assignee")


class TestRenderBadIssueBatchUI:
    """Tests for render_bad_issue_batch_ui function."""

    def test_render_ui_without_client(self, mock_streamlit):
        """Test UI renders error when client is not initialized."""
        mock_streamlit.button.return_value = True
        mock_client = MagicMock()
        mock_client.client = None

        render_bad_issue_batch_ui(mock_client)

        mock_streamlit.error.assert_called_with("GitLab client not initialized. Check URL and Token in the sidebar.")

    def test_render_ui_with_empty_client(self, mock_streamlit):
        """Test UI renders error with empty client."""
        mock_streamlit.button.return_value = True
        mock_client = MagicMock()
        mock_client.client = None

        render_bad_issue_batch_ui(mock_client)

        mock_streamlit.error.assert_called()

    @patch("modes.bad_issue.cached_batch_evaluate_issues")
    @patch("modes.bad_issue.BATCH_USERNAMES", ["user1", "user2"])
    def test_render_ui_batch_success(self, mock_cached, mock_client, mock_streamlit, sample_issue_rows):
        """Test successful batch report generation."""
        mock_streamlit.button.return_value = True
        mock_cached.return_value = sample_issue_rows

        render_bad_issue_batch_ui(mock_client)

        mock_streamlit.subheader.assert_called()
        mock_streamlit.expander.assert_called()
        mock_streamlit.dataframe.assert_called()

    @patch("modes.bad_issue.cached_batch_evaluate_issues")
    @patch("modes.bad_issue.BATCH_USERNAMES", ["user1"])
    def test_render_ui_with_exception(self, mock_cached, mock_client, mock_streamlit):
        """Test error handling during batch fetch."""
        mock_streamlit.button.return_value = True
        mock_cached.side_effect = Exception("API Error")

        render_bad_issue_batch_ui(mock_client)

        mock_streamlit.error.assert_called_with("Error during batch fetch: API Error")

    @patch("modes.bad_issue.cached_batch_evaluate_issues")
    @patch("modes.bad_issue.BATCH_USERNAMES", ["user1"])
    def test_render_ui_renders_metrics(self, mock_cached, mock_client, mock_streamlit, sample_issue_rows):
        """Test that UI renders with proper metrics."""
        mock_streamlit.button.return_value = True
        mock_cached.return_value = sample_issue_rows

        render_bad_issue_batch_ui(mock_client)

        assert mock_streamlit.subheader.call_count >= 2


class TestBatchUserDisplay:
    """Tests for batch user display section."""

    @patch("modes.bad_issue.BATCH_USERNAMES", ["user1", "user2", "user3"])
    def test_expander_contains_batch_count(self, mock_streamlit, mock_client):
        """Test expander displays correct batch user count."""
        mock_streamlit.button.return_value = False

        render_bad_issue_batch_ui(mock_client)

        mock_streamlit.expander.assert_called()


class TestDummyContextManagers:
    """Tests for DummyColumn and DummyExpander context managers."""

    def test_dummy_column_context_manager(self):
        """Test that DummyColumn works as a context manager."""
        col = DummyColumn()
        with col as c:
            assert c == col
        assert col.metric is not None

    def test_dummy_column_enter_returns_self(self):
        """Test that __enter__ returns the instance."""
        col = DummyColumn()
        result = col.__enter__()
        assert result is col

    def test_dummy_column_exit_returns_false(self):
        """Test that __exit__ returns False."""
        col = DummyColumn()
        result = col.__exit__(None, None, None)
        assert result is False

    def test_dummy_column_metric_mock(self):
        """Test that DummyColumn has a mocked metric attribute."""
        col = DummyColumn()
        assert isinstance(col.metric, MagicMock)
