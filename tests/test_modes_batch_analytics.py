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
        mock_st.radio = MagicMock(return_value="All Registered Interns")
        mock_st.multiselect = MagicMock(return_value=[])

        # Create column mocks if needed (removed in new code but might be used)
        col1, col2 = MagicMock(), MagicMock()
        mock_st.columns = MagicMock(return_value=(col1, col2))

        mock_st.text_area = MagicMock(return_value="")

        # Mock button
        def button_side_effect(label, **kwargs):
            if "Run Analysis" in label:
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
        mock_st.session_state = {}

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
    @patch("gitlab_compliance_checker.ui.batch.get_all_members_with_teams")
    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_render_success(self, mock_process, mock_get_members, mock_client, mock_streamlit, sample_unified_results):
        mock_get_members.return_value = [{"name": "User 1", "gitlab_username": "user1", "college_name": "ABC"}]
        mock_process.return_value = sample_unified_results

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.success.assert_called_with("Unified Batch processing complete!")
        mock_streamlit.dataframe.assert_called()
        mock_streamlit.download_button.assert_called()

    @patch("gitlab_compliance_checker.ui.batch.get_all_members_with_teams")
    def test_no_members_in_db(self, mock_get_members, mock_client, mock_streamlit):
        mock_get_members.return_value = []

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.warning.assert_called_with("⚠️ No interns found in the Roster Database. Please add users in the Admin panel first.")

    @patch("gitlab_compliance_checker.ui.batch.get_all_members_with_teams")
    @patch("gitlab_compliance_checker.ui.batch.batch.resolve_project_paths")
    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_repo_filter(self, mock_process, mock_resolve, mock_get_members, mock_client, mock_streamlit):
        mock_get_members.return_value = [{"name": "User 1", "gitlab_username": "user1", "college_name": "ABC"}]
        mock_streamlit.text_area.return_value = "group/repo"
        mock_resolve.return_value = ([123], [])
        mock_process.return_value = []

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_resolve.assert_called_once()
        mock_streamlit.info.assert_any_call("✅ Filtering by **1** project(s)")

    @patch("gitlab_compliance_checker.ui.batch.get_all_members_with_teams")
    @patch("gitlab_compliance_checker.ui.batch.batch.resolve_project_paths")
    def test_repo_resolve_fail(self, mock_resolve, mock_get_members, mock_client, mock_streamlit):
        mock_get_members.return_value = [{"name": "User 1", "gitlab_username": "user1", "college_name": "ABC"}]
        mock_streamlit.text_area.return_value = "bad/repo"
        mock_resolve.return_value = ([], ["bad/repo"])

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.error.assert_called_with("None of the entered repo paths could be resolved.")

    @patch("gitlab_compliance_checker.ui.batch.get_all_members_with_teams")
    @patch("gitlab_compliance_checker.ui.batch.cached_process_batch_users")
    def test_error_row(self, mock_process, mock_get_members, mock_client, mock_streamlit):
        mock_get_members.return_value = [{"name": "User 1", "gitlab_username": "user1", "college_name": "ABC"}]
        mock_process.return_value = [{"username": "user1", "status": "Error", "error": "Crash"}]

        batch_analytics.render_batch_analytics_ui(mock_client)

        mock_streamlit.dataframe.assert_called()
