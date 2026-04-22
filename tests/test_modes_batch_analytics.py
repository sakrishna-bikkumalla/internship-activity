from unittest.mock import MagicMock, patch

import pytest

import gitlab_compliance_checker.ui.batch as batch_analytics


@pytest.fixture
def mock_client():
    m = MagicMock()
    m.client = MagicMock()

    def mock_run_sync(coro):
        if hasattr(coro, "close"):
            coro.close()
        return []

    m._run_sync.side_effect = mock_run_sync
    return m


class DummySpinner:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class DummyExpander:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mock_streamlit():
    with patch("gitlab_compliance_checker.ui.batch.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.caption = MagicMock()
        mock_st.expander = MagicMock(return_value=DummyExpander())

        # Create column mocks
        col1, col2 = MagicMock(), MagicMock()
        mock_st.columns = MagicMock(return_value=(col1, col2))

        # Mock file_uploader (col1)
        mock_st.file_uploader.return_value = None
        col1.file_uploader.side_effect = lambda *args, **kwargs: mock_st.file_uploader(*args, **kwargs)

        # Mock text_area (col2 and main)
        # Default text_area side effect: first call "user1" (usernames), second call "" (no repos)
        mock_st.text_area.side_effect = ["user1", ""]
        col2.text_area.side_effect = lambda *args, **kwargs: mock_st.text_area(*args, **kwargs)

        # Mock button to return True for the analysis button specifically
        def button_side_effect(label, **kwargs):
            if label == "🚀 Run Unified Analysis":
                return True
            return False

        mock_st.button.side_effect = button_side_effect

        mock_st.spinner = MagicMock(return_value=DummySpinner())
        mock_st.error = MagicMock()
        mock_st.warning = MagicMock()
        mock_st.info = MagicMock()
        mock_st.success = MagicMock()
        mock_st.dataframe = MagicMock()
        mock_st.download_button = MagicMock()
        mock_st.markdown = MagicMock()
        yield mock_st


@pytest.fixture
def sample_unified_results():
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
                "mr_quality": {
                    "Closed MRs": 1,
                    "No Desc": 0,
                    "No Issues": 0,
                    "No Time Spent": 0,
                    "Failed Pipeline": 0,
                    "No Semantic Commits": 0,
                    "No Internal Review": 0,
                    "Merge > 2 Days": 0,
                    "Merge > 1 Week": 0,
                },
                "issue_quality": {
                    "Total Assigned": 1,
                    "Opened Issues": 0,
                    "Closed Issues": 1,
                    "No Desc": 0,
                    "No Labels": 0,
                    "No Milestone": 0,
                    "No Time Spent": 0,
                    "Long Open Time (>2 days)": 0,
                    "No Semantic Title": 0,
                },
            },
        }
    ]


class TestRenderBatchAnalyticsUI:
    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_render_success(self, mock_process, mock_client, mock_streamlit, sample_unified_results):
        mock_process.return_value = sample_unified_results

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.success.assert_called_with("Unified Batch processing complete!")
        mock_streamlit.dataframe.assert_called()
        mock_streamlit.download_button.assert_called()

    def test_no_usernames(self, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["", ""]

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.warning.assert_called_with("Please enter at least one username or upload a file.")

    @patch("gitlab_compliance_checker.ui.batch.batch.resolve_project_paths")
    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_repo_filter(self, mock_process, mock_resolve, mock_client, mock_streamlit):
        # First call to text_area for usernames, second for repo paths
        mock_streamlit.text_area.side_effect = ["user1", "group/repo"]
        mock_resolve.return_value = ([123], [])
        mock_process.return_value = []

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_resolve.assert_called_once()
        mock_streamlit.info.assert_any_call("✅ Filtering by **1** project(s)")

    @patch("gitlab_compliance_checker.ui.batch.batch.resolve_project_paths")
    def test_repo_resolve_fail(self, mock_resolve, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["user1", "bad/repo"]
        mock_resolve.return_value = ([], ["bad/repo"])

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.error.assert_called_with("None of the entered repo paths could be resolved.")

    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_error_row(self, mock_process, mock_client, mock_streamlit):
        mock_process.return_value = [{"username": "user1", "status": "Error", "error": "Crash"}]

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.dataframe.assert_called()

    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_csv_file_upload_first_column(self, mock_process, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["", ""]
        mock_file = MagicMock()
        mock_file.name = "users.csv"
        mock_file.seek = MagicMock()
        mock_file.read.return_value = b"user2\nuser3\n"
        mock_streamlit.file_uploader.return_value = mock_file
        mock_process.return_value = []

        batch_analytics.render_batch_analytics_ui(mock_client)

        # Verify that user2 and user3 were processed
        args, _ = mock_process.call_args
        usernames_processed = args[1]
        assert "user2" in usernames_processed
        assert "user3" in usernames_processed

    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_csv_file_upload_with_header_and_college(self, mock_process, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["", ""]
        mock_file = MagicMock()
        mock_file.name = "users.csv"
        mock_file.seek = MagicMock()
        mock_file.read.return_value = b"username,college\nuser2,ABC College\nuser3,XYZ University\n"
        mock_streamlit.file_uploader.return_value = mock_file
        mock_process.return_value = [
            {
                "username": "user2",
                "status": "Success",
                "data": {
                    "projects": {"personal": [], "contributed": []},
                    "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
                    "groups": [],
                    "mr_quality": {},
                    "issue_quality": {},
                },
            },
            {
                "username": "user3",
                "status": "Success",
                "data": {
                    "projects": {"personal": [], "contributed": []},
                    "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
                    "groups": [],
                    "mr_quality": {},
                    "issue_quality": {},
                },
            },
        ]

        batch_analytics.render_batch_analytics_ui(mock_client)

        args, _ = mock_process.call_args
        usernames_processed = args[1]
        assert "user2" in usernames_processed
        assert "user3" in usernames_processed

        rendered_df = mock_streamlit.dataframe.call_args.args[0]
        college_by_user = dict(zip(rendered_df["Username"], rendered_df["College"], strict=False))
        assert college_by_user["user2"] == "ABC College"
        assert college_by_user["user3"] == "XYZ University"

    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_csv_file_upload_without_header_uses_first_column(self, mock_process, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["", ""]
        mock_file = MagicMock()
        mock_file.name = "users.csv"
        mock_file.seek = MagicMock()
        mock_file.read.return_value = b"user2,ABC College\nuser3,XYZ University\n"
        mock_streamlit.file_uploader.return_value = mock_file
        mock_process.return_value = []

        batch_analytics.render_batch_analytics_ui(mock_client)

        args, _ = mock_process.call_args
        usernames_processed = args[1]
        assert "user2" in usernames_processed
        assert "user3" in usernames_processed

    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_malformed_upload_shows_error(self, mock_process, mock_client, mock_streamlit):
        mock_streamlit.text_area.side_effect = ["", ""]
        mock_file = MagicMock()
        mock_file.name = "users.csv"
        mock_streamlit.file_uploader.return_value = mock_file
        mock_process.return_value = []

        with patch("gitlab_compliance_checker.ui.batch._parse_uploaded_user_csv", side_effect=ValueError("Bad CSV")):
            batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.error.assert_any_call("Error reading uploaded CSV file: Bad CSV")
