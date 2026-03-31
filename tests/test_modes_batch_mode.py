from unittest.mock import MagicMock, patch

import pytest

from modes import batch_mode


@pytest.fixture
def mock_client():
    m = MagicMock()
    m.client = MagicMock()
    return m


class DummySpinner:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mock_streamlit():
    with patch("modes.batch_mode.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.text_area = MagicMock(return_value="")
        mock_st.button = MagicMock(return_value=False)
        mock_st.spinner = MagicMock(return_value=DummySpinner())
        mock_st.error = MagicMock()
        mock_st.warning = MagicMock()
        mock_st.info = MagicMock()
        mock_st.success = MagicMock()
        mock_st.dataframe = MagicMock()
        mock_st.download_button = MagicMock()
        mock_st.write = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.caption = MagicMock()
        yield mock_st


@pytest.fixture
def sample_success_results():
    return [
        {
            "username": "user1",
            "status": "Success",
            "data": {
                "projects": {"personal": [1], "contributed": []},
                "commit_stats": {"total": 10, "morning_commits": 5, "afternoon_commits": 5},
                "mr_stats": {"total": 2, "merged": 1, "opened": 1, "closed": 0},
                "issue_stats": {"total": 0, "opened": 0, "closed": 0},
                "groups": [],
            },
        }
    ]


@pytest.fixture
def sample_error_results():
    return [{"username": "user1", "status": "Error", "error": "Not Found"}]


class TestRenderBatchModeUI:
    """Tests for render_batch_mode_ui function - refactored to use fixtures and decorators."""

    @patch("modes.batch_mode.batch.process_batch_users")
    def test_icfai_success(self, mock_process, mock_client, mock_streamlit, sample_success_results):
        """Test ICFAI batch processing success."""
        mock_streamlit.text_area.side_effect = ["user1\nuser2", ""]
        mock_streamlit.button.return_value = True
        mock_process.return_value = sample_success_results

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.success.assert_called()
        mock_streamlit.dataframe.assert_called()

    @patch("modes.batch_mode.batch.process_batch_users")
    def test_rcts_success(self, mock_process, mock_client, mock_streamlit):
        """Test RCTS batch processing success."""
        mock_streamlit.text_area.side_effect = ["user1", ""]
        mock_streamlit.button.return_value = True
        mock_process.return_value = [
            {
                "username": "user1",
                "status": "Success",
                "data": {
                    "projects": {"personal": [1], "contributed": [2]},
                    "commit_stats": {"total": 5, "morning_commits": 1, "afternoon_commits": 0},
                    "mr_stats": {"total": 2, "merged": 1, "opened": 1, "closed": 0},
                    "issue_stats": {"total": 2, "opened": 1, "closed": 1},
                    "groups": [1],
                },
            }
        ]

        batch_mode.render_batch_mode_ui(mock_client, "RCTS")

        mock_streamlit.success.assert_called()

    @patch("modes.batch_mode.batch.resolve_project_paths")
    @patch("modes.batch_mode.batch.process_batch_users")
    def test_repo_filter(self, mock_process, mock_resolve, mock_client, mock_streamlit):
        """Test repo filtering functionality."""
        mock_streamlit.text_area.side_effect = ["user1", "group/repo"]
        mock_streamlit.button.return_value = True
        mock_resolve.return_value = ([123], [])
        mock_process.return_value = []

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.info.assert_called()

    @patch("modes.batch_mode.batch.resolve_project_paths")
    def test_repo_resolve_fail(self, mock_resolve, mock_client, mock_streamlit):
        """Test handling when repo paths cannot be resolved."""
        mock_streamlit.text_area.side_effect = ["user1", "bad/repo"]
        mock_streamlit.button.return_value = True
        mock_resolve.return_value = ([], ["bad/repo"])

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.error.assert_called()

    def test_no_usernames_warning(self, mock_client, mock_streamlit):
        """Test warning when no usernames provided."""
        mock_streamlit.text_area.side_effect = ["", ""]
        mock_streamlit.button.return_value = True

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.warning.assert_called_with("Please enter at least one username.")

    @patch("modes.batch_mode.batch.process_batch_users")
    def test_error_row(self, mock_process, mock_client, mock_streamlit, sample_error_results):
        """Test handling of error results."""
        mock_streamlit.text_area.side_effect = ["user1", ""]
        mock_streamlit.button.return_value = True
        mock_process.return_value = sample_error_results

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.dataframe.assert_called()

    @patch("modes.batch_mode.batch.process_batch_users")
    @patch("pandas.ExcelWriter")
    def test_excel_error_handling(self, mock_writer, mock_process, mock_client, mock_streamlit):
        """Test handling of Excel generation errors."""
        mock_streamlit.text_area.side_effect = ["user1", ""]
        mock_streamlit.button.return_value = True
        mock_process.return_value = []
        mock_writer.side_effect = Exception("XLSX Error")

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.error.assert_called()

    @patch("modes.batch_mode.batch.resolve_project_paths")
    def test_all_repo_paths_fail(self, mock_resolve, mock_client, mock_streamlit):
        """Test when all repo paths fail to resolve."""
        mock_streamlit.text_area.side_effect = ["user1", "bad/repo1\nbad/repo2"]
        mock_streamlit.button.return_value = True
        mock_resolve.return_value = ([], ["bad/repo1", "bad/repo2"])

        batch_mode.render_batch_mode_ui(mock_client, "ICFAI")

        mock_streamlit.error.assert_called()
