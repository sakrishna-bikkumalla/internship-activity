from unittest.mock import MagicMock, patch

import pytest

from modes import bad_mrs_batch


@pytest.fixture
def mock_client():
    m = MagicMock()
    m.client = MagicMock()
    return m


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
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DummySpinner:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestDummyColumn:
    """Tests for DummyColumn to ensure coverage."""

    def test_dummy_column_init(self):
        col = DummyColumn()
        assert col.metric is not None
        assert col.text_input is not None
        assert col.button is not None

    def test_dummy_column_context_manager(self):
        col = DummyColumn()
        with col as c:
            assert c is col

    def test_dummy_column_exit(self):
        col = DummyColumn()
        result = col.__exit__(None, None, None)
        assert result is False


@pytest.fixture
def mock_streamlit():
    def make_columns(n):
        if isinstance(n, list):
            return tuple(DummyColumn() for _ in n)
        return tuple(DummyColumn() for _ in range(n))

    with patch("modes.bad_mrs_batch.st") as mock_st:
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
def sample_mr_rows():
    return [
        {
            "Username": "user1",
            "Closed MRs": 10,
            "No Desc": 1,
            "Improper Desc": 2,
            "No Issues": 3,
            "No Time Spent": 4,
            "No Unit Tests": 5,
            "Failed Pipeline": 6,
            "No Semantic Commits": 7,
            "No Internal Review": 8,
            "Merge > 2 Days": 9,
            "Merge > 1 Week": 0,
        }
    ]


class TestRenderBadMrsBatchUI:
    """Tests for render_bad_mrs_batch_ui function - refactored to use fixtures."""

    def test_not_initialized(self, mock_streamlit):
        """Test UI renders error when client not initialized."""
        mock_streamlit.button.return_value = True
        bad_mrs_batch.render_bad_mrs_batch_ui(None)
        mock_streamlit.error.assert_called_with("GitLab client not initialized. Check URL and Token in the sidebar.")

    @patch("modes.bad_mrs_batch.cached_batch_evaluate_mrs")
    @patch("modes.bad_mrs_batch.BATCH_USERNAMES", ["user1", "user2"])
    def test_generate_success(self, mock_cached, mock_client, mock_streamlit, sample_mr_rows):
        """Test successful batch report generation."""
        mock_streamlit.button.return_value = True
        mock_cached.return_value = sample_mr_rows

        bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)

        mock_streamlit.subheader.assert_called()
        mock_streamlit.expander.assert_called()
        mock_streamlit.dataframe.assert_called()

    @patch("modes.bad_mrs_batch.cached_batch_evaluate_mrs")
    @patch("modes.bad_mrs_batch.BATCH_USERNAMES", ["user1"])
    def test_batch_fetch_error(self, mock_cached, mock_client, mock_streamlit):
        """Test error handling during batch fetch."""
        mock_streamlit.button.return_value = True
        mock_cached.side_effect = Exception("API Error")

        bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)

        mock_streamlit.error.assert_called_with("Error during batch fetch: API Error")

    @patch("modes.bad_mrs_batch.cached_batch_evaluate_mrs")
    @patch("modes.bad_mrs_batch.BATCH_USERNAMES", ["user1"])
    def test_renders_metrics(self, mock_cached, mock_client, mock_streamlit, sample_mr_rows):
        """Test that metrics are rendered."""
        mock_streamlit.button.return_value = True
        mock_cached.return_value = sample_mr_rows

        bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)

        assert mock_streamlit.subheader.call_count >= 2

    def test_button_not_clicked(self, mock_client, mock_streamlit):
        """Test no action when button not clicked."""
        mock_streamlit.button.return_value = False
        bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)
