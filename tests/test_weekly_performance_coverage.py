import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from gitlab_compliance_checker.ui import weekly_performance

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_summary_card(mock_st):
    weekly_performance._render_summary_card(1, 2, 3, "1h")
    mock_st.markdown.assert_called()

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_activity_slots(mock_st):
    weekly_performance._render_activity_slots([9, 10], [9, 10, 11])
    mock_st.markdown.assert_called()

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_activity_slots_with_events(mock_st):
    events = {9: [{"type": "mr", "title": "Test MR", "url": "http://test"}]}
    weekly_performance._render_activity_slots([9], [9], events_by_hour=events)
    mock_st.markdown.assert_called()

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_activity_slots_strict_idle(mock_st):
    weekly_performance._render_activity_slots([], [9, 10], use_strict_mode=True)
    mock_st.markdown.assert_called()

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_group_member_selector(mock_st):
    members = [{"name": "User", "username": "user"}]
    mock_st.session_state = {"fetched_group_members": members}
    mock_st.selectbox.return_value = "User (@user)"
    res = weekly_performance._render_group_member_selector()
    assert res["gitlab_username"] == "user"

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
@patch("gitlab_compliance_checker.ui.weekly_performance._init_state")
@patch("gitlab_compliance_checker.ui.weekly_performance._render_date_selector")
@patch("gitlab_compliance_checker.ui.weekly_performance.get_member_by_username")
@patch("gitlab_compliance_checker.ui.weekly_performance.get_all_members_with_teams")
def test_render_weekly_performance_ui_no_data(mock_all, mock_one, mock_date, mock_init, mock_st):
    mock_date.return_value = (date(2024, 1, 1), "Single Day")
    mock_st.session_state = {"user_role": "admin", "fetched_group_members": []}
    mock_all.return_value = []
    weekly_performance.render_weekly_performance_ui(MagicMock())
    # Should call st.info since no interns or group members
    assert mock_st.info.called

def test_init_state_full():
    with patch("gitlab_compliance_checker.ui.weekly_performance.st") as mock_st:
        mock_st.session_state = {}
        weekly_performance._init_state()
        assert "wp_view_mode" in mock_st.session_state
        assert "wp_interns" in mock_st.session_state
