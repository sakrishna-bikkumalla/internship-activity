import datetime
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st

from gitlab_compliance_checker.ui import leaderboard


@pytest.fixture
def mock_client():
    c = MagicMock()
    # Mock _run_sync to return results immediately
    c._run_sync.side_effect = lambda x: []
    return c


def test_calculate_score():
    # 10*1 + 2*5 + 5*2 + 3*3 = 10 + 10 + 10 + 9 = 39
    assert leaderboard._calculate_score(10, 2, 5, 3) == 39


def test_extract_member_row_success():
    result = {
        "username": "user1",
        "status": "Success",
        "data": {
            "commit_stats": {"total": 10},
            "mr_stats": {"merged": 2, "total": 5},
            "issue_stats": {"closed": 3},
            "groups": ["group1"],
        },
    }
    row = leaderboard._extract_member_row(result)
    assert row["Username"] == "user1"
    assert row["Score"] == 39
    assert row["Groups"] == 1


def test_extract_member_row_error():
    result = {"username": "user1", "status": "Error", "error": "Timeout"}
    row = leaderboard._extract_member_row(result)
    assert row["Status"] == "Error"
    assert row["Score"] == 0


def test_aggregate_team_totals():
    member_rows = [
        {"Score": 10, "Total Commits": 5, "MR Merged": 1, "Issues Closed": 1},
        {"Score": 20, "Total Commits": 10, "MR Merged": 2, "Issues Closed": 2},
    ]
    totals = leaderboard._aggregate_team_totals(member_rows)
    assert totals["Team Score"] == 30
    assert totals["Total Commits"] == 15


@patch("streamlit.date_input")
def test_render_date_filter(mock_date_input):
    mock_date_input.side_effect = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 7)]
    with patch("streamlit.columns", return_value=[MagicMock(), MagicMock(), MagicMock()]):
        # Mock session state
        st.session_state["_lb_from_date"] = None
        st.session_state["_lb_to_date"] = None
        
        since, until = leaderboard._render_date_filter()
        assert since.startswith("2024-01-01")
        assert until.startswith("2024-01-07")


def test_load_rank_badge_svg():
    # Test fallback
    with patch("pathlib.Path.exists", return_value=False):
        assert leaderboard._load_rank_badge_svg(1) == ""


def test_render_activity_heatmap():
    with patch("streamlit.markdown") as m_md:
        leaderboard._render_activity_heatmap({"2024-01-01": 5})
        assert m_md.called


def test_render_team_result():
    with patch("streamlit.subheader"), \
         patch("streamlit.columns", return_value=[MagicMock() for _ in range(7)]), \
         patch("streamlit.metric"), \
         patch("streamlit.dataframe"), \
         patch("streamlit.expander"), \
         patch("streamlit.popover", create=True), \
         patch("streamlit.markdown"):
        
        totals = {
            "Team Score": 10,
            "Total Commits": 5,
            "MR Merged": 2,
            "Issues Closed": 1
        }
        leaderboard._render_team_result("Team A", "Project X", [{"Score": 10, "Username": "u1"}], totals)
        # Should finish without error
