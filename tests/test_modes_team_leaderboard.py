from unittest.mock import MagicMock, patch

import pytest
import streamlit as st

from modes import team_leaderboard


@pytest.fixture
def mock_client():
    return MagicMock()


def mock_columns(spec):
    return [MagicMock() for _ in range(len(spec) if isinstance(spec, list) else spec)]


def test_init_state():
    with patch("streamlit.session_state", {}):
        team_leaderboard._init_state()
        assert "teams" in st.session_state
        assert len(st.session_state["teams"]) > 0


def test_calculate_score():
    # score = (total_commits * 1) + (merged_mrs * 5) + (total_mrs * 2) + (issues_closed * 3)
    assert team_leaderboard._calculate_score(10, 2, 5, 3) == 10 * 1 + 2 * 5 + 5 * 2 + 3 * 3  # 10+10+10+9=39
    assert team_leaderboard._calculate_score(0, 0, 0, 0) == 0


def test_extract_member_row_success():
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
    row = team_leaderboard._extract_member_row(result)
    assert row["Username"] == "user1"
    assert row["Score"] == 39
    assert row["Groups"] == 2


def test_extract_member_row_error():
    result = {"username": "user1", "status": "Error", "error": "Not Found"}
    row = team_leaderboard._extract_member_row(result)
    assert row["Status"] == "Error"
    assert row["Score"] == 0


def test_aggregate_team_totals():
    rows = [
        {"Score": 10, "Total Commits": 5, "MR Merged": 1, "Issues Closed": 1},
        {"Score": 20, "Total Commits": 10, "MR Merged": 2, "Issues Closed": 2},
    ]
    totals = team_leaderboard._aggregate_team_totals(rows)
    assert totals["Team Score"] == 30
    assert totals["Total Commits"] == 15


def test_build_ranking_rows():
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
    ranked = team_leaderboard._build_ranking_rows(team_data)
    assert ranked[0]["Team Name"] == "Team B"
    assert ranked[0]["Rank"] == 1
    assert ranked[1]["Team Name"] == "Team A"
    assert ranked[1]["Rank"] == 2


def test_build_individual_rows_and_badges():
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
                },
                {
                    "Username": "u2",
                    "Status": "Success",
                    "Score": 50,
                    "Total Commits": 20,
                    "MR Merged": 5,
                    "Issues Closed": 2,
                },
            ],
            {},
        )
    }
    # all_members.sort key is Score
    # u1 should have sprint_star (highest score), top_committer, merge_master, team_player
    # but MAX_BADGES = 3
    # Wait, team_player is added first.
    # then sprint_star, top_committer, merge_master.
    # so u1 should have: team_player, sprint_star, top_committer.

    rows = team_leaderboard._build_individual_rows(team_data)
    u1 = next(r for r in rows if r["Username"] == "u1")
    assert len(u1["Badges"]) <= 3
    assert "team_player" in u1["Badges"]


def test_validate_json_teams():
    with patch("streamlit.session_state", {"teams": []}):
        # Mocking existing names
        valid_json = {
            "teams": [{"team_name": "Team 1", "project_name": "P1", "members": [{"name": "M1", "username": "u1"}]}]
        }
        teams, err = team_leaderboard._validate_json_teams(valid_json)
        assert err == ""
        assert len(teams) == 1


def test_validate_json_teams_duplicate():
    with patch("streamlit.session_state", {"teams": [{"team_name": "T1"}]}):
        dup_json = {"teams": [{"team_name": "t1", "project_name": "P", "members": [{"username": "u"}]}]}
        teams, err = team_leaderboard._validate_json_teams(dup_json)
        assert "already exists" in err


def test_load_rank_badge_svg_not_found():
    with patch("pathlib.Path.exists", return_value=False):
        assert team_leaderboard._load_rank_badge_svg(1) == ""


def test_render_team_leaderboard_basic(mock_client):
    with patch("streamlit.session_state", {"teams": []}):
        with patch("streamlit.columns", side_effect=mock_columns):
            with patch("streamlit.button", return_value=False):
                team_leaderboard.render_team_leaderboard(mock_client)


def test_render_create_team_form_add_member():
    state = {
        "teams": [],
        "edit_team_index": None,
        "_lb_show_create_form": True,
        "_lb_show_upload_form": False,
        "_lb_draft_members": [],
    }
    with patch("streamlit.session_state", state):
        with patch("streamlit.columns", side_effect=mock_columns):
            with patch("streamlit.text_input", return_value="user1"):
                with patch("streamlit.number_input", return_value=123):
                    # Mocking the "Add Member" button
                    def mock_btn(label, key=None, **kwargs):
                        return key == "_lb_create_add_member"

                    with patch("streamlit.button", side_effect=mock_btn):
                        with patch("streamlit.rerun") as mock_rerun:
                            team_leaderboard._render_create_team_form()
                            assert len(state["_lb_draft_members"]) == 1
                            mock_rerun.assert_called_once()


def test_render_edit_form_update():
    state = {
        "teams": [{"team_name": "T1", "project_name": "P1", "members": [{"username": "u1"}]}],
        "edit_team_index": 0,
        "_lb_edit_draft": {"team_name": "T1", "members": [{"username": "u1"}], "_source_index": 0},
    }
    with patch("streamlit.session_state", state):
        with patch("streamlit.columns", side_effect=mock_columns):
            with patch("streamlit.text_input", return_value="T1-New"):

                def mock_btn(label, key=None, **kwargs):
                    return key == "_lb_edit_save"

                with patch("streamlit.button", side_effect=mock_btn):
                    with patch("streamlit.rerun"):
                        team_leaderboard._render_edit_form(0)
                        assert state["teams"][0]["team_name"] == "T1-New"


def test_get_contribution_index_uses_icfai_group_window():
    with patch("streamlit.session_state", {}):
        active_days, total_days, consistency = team_leaderboard._get_contribution_index({}, "prav2702")
    expected_total = (team_leaderboard.datetime.date.today() - team_leaderboard.ICFAI_START_DATE).days + 1
    assert active_days == 0
    assert total_days == expected_total
    assert consistency == 0.0


def test_get_contribution_index_uses_rcts_group_window():
    with patch("streamlit.session_state", {}):
        active_days, total_days, consistency = team_leaderboard._get_contribution_index({}, "vai5h")
    expected_total = (team_leaderboard.datetime.date.today() - team_leaderboard.RCTS_START_DATE).days + 1
    assert active_days == 0
    assert total_days == expected_total
    assert consistency == 0.0
