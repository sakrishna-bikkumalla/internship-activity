from unittest.mock import MagicMock, patch

import pytest
import streamlit as st


@pytest.fixture(autouse=True)
def reimport_leaderboard(monkeypatch):
    from internship_activity_tracker.ui import leaderboard

    # We don't delete from sys.modules as it breaks mock.patch in Python 3.12+
    # We just return the already imported module. Any required session state
    # cleanup should be done before the tests run.
    return leaderboard


@pytest.fixture
def mock_client():
    return MagicMock()


def mock_columns(spec):
    return [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]


def test_init_state(reimport_leaderboard):
    with patch("streamlit.session_state", {}):
        # We need to mock it again here because init_state calls it
        with patch("internship_activity_tracker.ui.leaderboard.get_all_teams_with_members", return_value=[]):
            reimport_leaderboard._init_state()
            assert "teams" in st.session_state


def test_calculate_score(reimport_leaderboard):
    assert reimport_leaderboard._calculate_score(10, 2, 5, 3) == 39


def test_extract_member_row_success(reimport_leaderboard):
    result = {
        "username": "user1",
        "status": "Success",
        "data": {
            "commit_stats": {"total": 10, "morning_commits": 5, "afternoon_commits": 5},
            "mr_stats": {"total": 5, "merged": 2, "opened": 3, "closed": 0},
            "issue_stats": {"total": 4, "closed": 3},
            "groups": [1, 2],
        },
    }
    row = reimport_leaderboard._extract_member_row(result)
    assert row["Username"] == "user1"
    assert row["Score"] == 39


def test_aggregate_team_totals(reimport_leaderboard):
    rows = [
        {"Score": 10, "Total Commits": 5, "MR Merged": 1, "Issues Closed": 1},
        {"Score": 20, "Total Commits": 10, "MR Merged": 2, "Issues Closed": 2},
    ]
    totals = reimport_leaderboard._aggregate_team_totals(rows)
    assert totals["Team Score"] == 30


def test_build_ranking_rows(reimport_leaderboard):
    team_data = {
        "Team A": (
            {"project_name": "P1"},
            [],
            {"Team Score": 100, "Total Commits": 50, "MR Merged": 10, "Issues Closed": 5},
        ),
        "Team B": (
            {"project_name": "P2"},
            [],
            {"Team Score": 200, "Total Commits": 100, "MR Merged": 20, "Issues Closed": 10},
        ),
    }
    ranked = reimport_leaderboard._build_ranking_rows(team_data)
    assert ranked[0]["Team Name"] == "Team B"


def test_build_individual_rows_and_badges(reimport_leaderboard):
    team_data = {
        "Team A": (
            {},
            [
                {
                    "Username": "u1",
                    "Status": "Success",
                    "Score": 100,
                    "Total Commits": 50,
                    "MR Merged": 10,
                    "Issues Closed": 5,
                    "Active Days": 5,
                    "Consistency": 0.5,
                }
            ],
            {},
        )
    }
    rows = reimport_leaderboard._build_individual_rows(team_data)
    assert len(rows) == 1


def test_render_team_leaderboard_basic(reimport_leaderboard, mock_client):
    with patch("streamlit.session_state", {"teams": []}):
        with patch("streamlit.columns", side_effect=mock_columns):
            with patch("streamlit.button", return_value=False):
                # Mock the service function directly in the module
                with (
                    patch("internship_activity_tracker.ui.leaderboard.get_all_batches", return_value=[], create=True),
                    patch(
                        "internship_activity_tracker.ui.leaderboard.get_teams_by_batch", return_value=[], create=True
                    ),
                    patch(
                        "internship_activity_tracker.ui.leaderboard.get_members_by_team", return_value=[], create=True
                    ),
                    patch("internship_activity_tracker.ui.leaderboard.get_all_teams_with_members", return_value=[]),
                ):
                    reimport_leaderboard.render_batch_analytics(mock_client)
