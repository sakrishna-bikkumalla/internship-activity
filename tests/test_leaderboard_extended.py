from unittest.mock import MagicMock, patch

import pytest

from internship_activity_tracker.ui import leaderboard


@pytest.fixture(autouse=True)
def mock_db_service():
    with patch("internship_activity_tracker.ui.leaderboard.get_all_teams_with_members", return_value=[]):
        yield


def test_init_state_extended():
    # Test initialization when some keys exist but others don't
    # Set _lb_page to "Workspace" so it doesn't try to reload teams from DB and overwrite our test state
    state = {"teams": ["existing"], "_lb_page": "Workspace"}
    with patch("internship_activity_tracker.ui.leaderboard.st.session_state", state):
        leaderboard._init_state()
        assert state["teams"] == ["existing"]
        assert "_lb_show_create_form" in state
        assert state["_lb_show_create_form"] is False


def test_calculate_score():
    # score = total_commits * 1 + merged_mrs * 5 + total_mrs * 2 + issues_closed * 3
    # 10*1 + 2*5 + 5*2 + 3*3 = 10 + 10 + 10 + 9 = 39
    assert leaderboard._calculate_score(10, 2, 5, 3) == 39


@patch("internship_activity_tracker.ui.leaderboard.st")
def test_render_sidebar_controls(mock_st):
    import datetime
    # Mock columns to return 3 mocks
    mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    mock_st.date_input.side_effect = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 10)]
    
    state = {"_lb_from_date": None, "_lb_to_date": None, "_lb_clear_dates_requested": False}
    with patch("internship_activity_tracker.ui.leaderboard.st.session_state", state):
        leaderboard._render_date_filter()
        # Verify date_input was called for From and To dates
        assert mock_st.date_input.call_count >= 2
