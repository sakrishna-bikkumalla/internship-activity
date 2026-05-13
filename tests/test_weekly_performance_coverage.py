from datetime import date
from unittest.mock import MagicMock, patch

from internship_activity_tracker.ui import weekly_performance


@patch("internship_activity_tracker.ui.weekly_performance.st")
def test_render_summary_card(mock_st):
    weekly_performance._render_summary_card(1, 2, 3, "1h")
    mock_st.markdown.assert_called()

@patch("internship_activity_tracker.ui.weekly_performance.st")
def test_render_activity_slots(mock_st):
    weekly_performance._render_activity_slots([9, 10], [9, 10, 11])
    mock_st.markdown.assert_called()

@patch("internship_activity_tracker.ui.weekly_performance.st")
def test_render_activity_slots_with_events(mock_st):
    events = {9: [{"type": "mr", "title": "Test MR", "url": "http://test"}]}
    weekly_performance._render_activity_slots([9], [9], events_by_hour=events)
    mock_st.markdown.assert_called()

@patch("internship_activity_tracker.ui.weekly_performance.st")
def test_render_activity_slots_strict_idle(mock_st):
    weekly_performance._render_activity_slots([], [9, 10], use_strict_mode=True)
    mock_st.markdown.assert_called()

@patch("internship_activity_tracker.ui.weekly_performance.st")
@patch("internship_activity_tracker.ui.weekly_performance.get_all_batches")
@patch("internship_activity_tracker.ui.weekly_performance.get_teams_by_batch")
@patch("internship_activity_tracker.ui.weekly_performance.get_members_by_team")
def test_render_hierarchical_selector(mock_members, mock_teams, mock_batches, mock_st):
    mock_batches.return_value = [{"id": 1, "name": "Batch 1"}]
    mock_teams.return_value = [{"id": 1, "name": "Team 1"}]
    mock_members.return_value = [{"name": "User", "gitlab_username": "user"}]
    mock_st.session_state = {
        "_wp_selected_batch": "Batch 1",
        "_wp_selected_teams": ["All Teams"],
        "_wp_selected_members": ["All Members"],
    }
    mock_st.selectbox.return_value = "Batch 1"
    mock_st.multiselect.side_effect = [["All Teams"], ["All Members"]]
    mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    
    res = weekly_performance._render_hierarchical_selector([{"name": "User", "gitlab_username": "user"}])
    assert len(res) == 1
    assert res[0]["gitlab_username"] == "user"

@patch("internship_activity_tracker.ui.weekly_performance.st")
@patch("internship_activity_tracker.ui.weekly_performance.get_all_batches")
@patch("internship_activity_tracker.ui.weekly_performance.get_teams_by_batch")
@patch("internship_activity_tracker.ui.weekly_performance.get_members_by_team")
def test_render_hierarchical_selector_no_matches(mock_members, mock_teams, mock_batches, mock_st):
    mock_batches.return_value = [{"id": 1, "name": "Batch 1"}]
    mock_teams.return_value = [{"id": 1, "name": "Team 1"}]
    mock_members.return_value = []
    mock_st.session_state = {
        "_wp_selected_batch": "Batch 1",
        "_wp_selected_teams": ["Team 1"],
        "_wp_selected_members": ["Specific Member"],
    }
    mock_st.selectbox.return_value = "Batch 1"
    mock_st.multiselect.side_effect = [["Team 1"], ["Specific Member"]]
    mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    
    res = weekly_performance._render_hierarchical_selector([{"name": "User", "gitlab_username": "user", "team_name": "Team 1"}])
    # Should return empty list because "Specific Member" doesn't match "User"
    assert len(res) == 0

@patch("internship_activity_tracker.ui.weekly_performance.st")
@patch("internship_activity_tracker.ui.weekly_performance.get_all_batches")
@patch("internship_activity_tracker.ui.weekly_performance.get_teams_by_batch")
@patch("internship_activity_tracker.ui.weekly_performance.get_members_by_team")
def test_render_hierarchical_selector_single_mode(mock_members, mock_teams, mock_batches, mock_st):
    mock_batches.return_value = [{"id": 1, "name": "Batch 1"}]
    mock_teams.return_value = [{"id": 1, "name": "Team 1"}]
    mock_members.return_value = [{"name": "User", "gitlab_username": "user"}]
    mock_st.session_state = {
        "_wp_selected_batch": "Batch 1",
        "_wp_selected_teams": ["Team 1"],
        "_wp_selected_members": ["User (@user)"],
    }
    mock_st.selectbox.return_value = "Batch 1"
    mock_st.multiselect.side_effect = [["Team 1"], ["User (@user)"]]
    mock_st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    
    res = weekly_performance._render_hierarchical_selector([{"name": "User", "gitlab_username": "user", "team_name": "Team 1"}])
    assert len(res) == 1
    assert res[0]["gitlab_username"] == "user"

@patch("internship_activity_tracker.ui.weekly_performance.st")
@patch("internship_activity_tracker.ui.weekly_performance._init_state")
@patch("internship_activity_tracker.ui.weekly_performance._render_date_selector")
@patch("internship_activity_tracker.ui.weekly_performance.get_member_by_username")
@patch("internship_activity_tracker.ui.weekly_performance.get_all_members_with_teams")
def test_render_weekly_performance_ui_no_data(mock_all, mock_one, mock_date, mock_init, mock_st):
    mock_date.return_value = (date(2024, 1, 1), "Single Day")
    mock_st.session_state = {"user_role": "admin", "fetched_group_members": []}
    mock_all.return_value = []
    weekly_performance.render_weekly_performance_ui(MagicMock())
    # Should call st.info since no interns or group members
    assert mock_st.info.called

def test_init_state_full():
    with patch("internship_activity_tracker.ui.weekly_performance.st") as mock_st:
        mock_st.session_state = {}
        weekly_performance._init_state()
        assert "wp_view_mode" in mock_st.session_state
        assert "_wp_selected_batch" in mock_st.session_state
        assert "_wp_selected_teams" in mock_st.session_state
