from unittest.mock import MagicMock, patch

import pytest

from internship_activity_tracker.ui import batch as batch_analytics


@pytest.fixture
def mock_client():
    m = MagicMock()

    def mock_run_sync(coro):
        if hasattr(coro, "close"):
            coro.close()
        return []

    m._run_sync.side_effect = mock_run_sync
    return m


class DummyCM:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


@pytest.fixture
def mock_streamlit():
    with patch("internship_activity_tracker.ui.batch.st") as mock_st:
        mock_st.session_state = {
            "_ba_selected_batch": "All Batches",
            "_ba_selected_teams": ["All Teams"],
            "_ba_selected_members": ["All Members"],
            "repo_paths": "",
            "repo_paths_raw": "",
            "overrides_raw": "",
        }
        mock_st.subheader = MagicMock()
        mock_st.caption = MagicMock()
        mock_st.expander = MagicMock(return_value=DummyCM())
        mock_st.popover = MagicMock(return_value=DummyCM())
        mock_st.spinner = MagicMock(return_value=DummyCM())
        mock_st.radio = MagicMock(return_value="All Registered Interns")
        
        mock_st.multiselect = MagicMock(return_value=["All Members", "All Teams"])
        mock_st.selectbox = MagicMock(return_value="All Batches")
        mock_st.columns = MagicMock(side_effect=lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))])
        mock_st.text_area = MagicMock(return_value="")
        mock_st.button = MagicMock(return_value=True)
        mock_st.success = MagicMock()
        mock_st.warning = MagicMock()
        mock_st.error = MagicMock()
        mock_st.info = MagicMock()
        mock_st.dataframe = MagicMock()
        mock_st.download_button = MagicMock()
        mock_st.rerun = MagicMock()
        
        yield mock_st


class TestRenderBatchAnalyticsUI:
    def test_render_success(self, mock_client, mock_streamlit):
        sample_results = [{"username": "user1", "status": "Success", "data": {}}]
        with patch("internship_activity_tracker.ui.batch.get_all_members_with_teams", return_value=[{"name": "User 1", "gitlab_username": "user1"}]), \
             patch("internship_activity_tracker.ui.batch.get_all_batches", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_teams_by_batch", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_members_by_team", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.cached_process_batch_users", return_value=sample_results):
            
            batch_analytics.render_batch_analytics_ui(mock_client)
            mock_streamlit.success.assert_called()

    def test_no_members_in_db(self, mock_client, mock_streamlit):
        with patch("internship_activity_tracker.ui.batch.get_all_members_with_teams", return_value=[]):
            batch_analytics.render_batch_analytics_ui(mock_client)
            mock_streamlit.warning.assert_called()

    def test_repo_filter(self, mock_client, mock_streamlit):
        sample_results = [{"username": "user1", "status": "Success", "data": {}}]
        with patch("internship_activity_tracker.ui.batch.get_all_members_with_teams", return_value=[{"name": "User 1", "gitlab_username": "user1"}]), \
             patch("internship_activity_tracker.ui.batch.get_all_batches", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_teams_by_batch", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_members_by_team", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.batch.resolve_project_paths", return_value=([123], [])), \
             patch("internship_activity_tracker.ui.batch.cached_process_batch_users", return_value=sample_results):
            
            mock_streamlit.text_area.return_value = "group/repo"
            batch_analytics.render_batch_analytics_ui(mock_client)
            mock_streamlit.info.assert_called()

    def test_repo_resolve_fail(self, mock_client, mock_streamlit):
        with patch("internship_activity_tracker.ui.batch.get_all_members_with_teams", return_value=[{"name": "User 1", "gitlab_username": "user1"}]), \
             patch("internship_activity_tracker.ui.batch.get_all_batches", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_teams_by_batch", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.get_members_by_team", return_value=[]), \
             patch("internship_activity_tracker.ui.batch.batch.resolve_project_paths", return_value=([], ["bad/repo"])):
            
            mock_streamlit.text_area.return_value = "bad/repo"
            batch_analytics.render_batch_analytics_ui(mock_client)
            mock_streamlit.error.assert_called()


def test_init_ba_state():
    with patch("internship_activity_tracker.ui.batch.st") as mock_st:
        mock_st.session_state = {}
        batch_analytics._init_ba_state()
        assert "_ba_selected_batch" in mock_st.session_state
        assert "_ba_selected_teams" in mock_st.session_state
        assert "_ba_selected_members" in mock_st.session_state
