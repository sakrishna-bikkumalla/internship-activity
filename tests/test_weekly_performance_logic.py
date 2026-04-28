import pytest
from unittest.mock import MagicMock, patch
from gitlab_compliance_checker.ui import weekly_performance

@patch("gitlab_compliance_checker.ui.weekly_performance.st.markdown")
def test_render_summary_card(mock_markdown):
    weekly_performance._render_summary_card(1, 2, 3, "2h 30m")
    mock_markdown.assert_called_once()
    html = mock_markdown.call_args[0][0]
    assert "2h 30m" in html
    assert "3" in html

@patch("gitlab_compliance_checker.ui.weekly_performance.st.markdown")
def test_render_activity_slots_basic(mock_markdown):
    # Test normal active slots
    weekly_performance._render_activity_slots(active_hours=[9, 10], slots=[9, 10, 11])
    mock_markdown.assert_called_once()
    html = mock_markdown.call_args[0][0]
    assert "slot-active" in html
    assert "09:00" in html

@patch("gitlab_compliance_checker.ui.weekly_performance.st.markdown")
def test_render_activity_slots_yellow_streak(mock_markdown):
    # 4 consecutive idle slots should trigger yellow in strict mode
    # Slots: 9(A), 10(I), 11(I), 12(I), 13(I), 14(A)
    weekly_performance._render_activity_slots(
        active_hours=[9, 14], 
        slots=[9, 10, 11, 12, 13, 14],
        use_strict_mode=True
    )
    html = mock_markdown.call_args[0][0]
    assert "slot-yellow" in html

@patch("gitlab_compliance_checker.ui.weekly_performance.st.markdown")
def test_render_activity_slots_total_idle(mock_markdown):
    # No active hours at all should trigger red idle
    weekly_performance._render_activity_slots(
        active_hours=[], 
        slots=[9, 10],
        use_strict_mode=True
    )
    html = mock_markdown.call_args[0][0]
    assert "slot-red-idle" in html

def test_init_state():
    state = {}
    with patch("gitlab_compliance_checker.ui.weekly_performance.st.session_state", state):
        weekly_performance._init_state()
        assert "wp_interns" in state
        assert state["wp_view_mode"] == "7 Day Range"

@patch("gitlab_compliance_checker.ui.weekly_performance.st")
def test_render_date_selector(mock_st):
    import datetime
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    mock_st.date_input.return_value = datetime.date(2024, 1, 1)
    # Just verify it doesn't crash
    res = weekly_performance._render_date_selector()
    assert res is not None
