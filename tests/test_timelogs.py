from datetime import date
from unittest.mock import MagicMock

import pytest

from internship_activity_tracker.infrastructure.gitlab.timelogs import (
    aggregate_daily_time,
    fetch_user_timelogs_from_projects,
    format_time_spent,
)


def test_aggregate_daily_time():
    logs = [
        {"spent_at": "2024-05-01T10:00:00Z", "time_spent": 3600},
        {"date": "2024-05-01", "time_spent": 1800},
        {"spent_at": "2024-05-02T12:00:00Z", "time_spent": 7200},
    ]
    daily = aggregate_daily_time(logs)
    assert daily["2024-05-01"] == 5400
    assert daily["2024-05-02"] == 7200


def test_format_time_spent():
    assert format_time_spent(3600) == "1 hr 0 min"
    assert format_time_spent(3660) == "1 hr 1 min"
    assert format_time_spent(90) == "1 min"
    assert format_time_spent(0) == "0 min"


def test_fetch_user_timelogs_from_projects():
    mock_client = MagicMock()
    # Mock global search
    mock_client._get.side_effect = [
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}],  # Global
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}],  # Project 1 (Duplicate)
        [{"id": 2, "time_spent": 1800, "spent_at": "2024-05-02"}],  # Project 2
    ]

    projects = [{"id": 101}, {"id": 102}]
    logs = fetch_user_timelogs_from_projects(mock_client, 123, projects, date(2024, 5, 1), date(2024, 5, 2))

    assert len(logs) == 2
    assert {log["id"] for log in logs} == {1, 2}


@pytest.mark.asyncio
async def test_fetch_user_timelogs_from_projects_async():
    from unittest.mock import AsyncMock

    mock_client = MagicMock()
    mock_client._async_get = AsyncMock()
    # Mock global search
    mock_client._async_get.side_effect = [
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}],  # Global
        [{"id": 2, "time_spent": 1800, "spent_at": "2024-05-02"}],  # Project 1
        [{"id": 3, "time_spent": 900, "spent_at": "2024-05-02"}],  # Project 2
    ]

    projects = [{"id": 101}, {"id": 102}]
    from internship_activity_tracker.infrastructure.gitlab.timelogs import fetch_user_timelogs_from_projects_async

    logs = await fetch_user_timelogs_from_projects_async(mock_client, 123, projects, date(2024, 5, 1), date(2024, 5, 2))

    assert len(logs) == 3
    assert {log["id"] for log in logs} == {1, 2, 3}


def test_aggregate_daily_time_categorized():
    from internship_activity_tracker.infrastructure.gitlab.timelogs import aggregate_daily_time_categorized

    timelogs = [
        {"spent_at": "2024-05-01T10:00:00Z", "time_spent": 3600, "issue_id": 10},
        {"spent_at": "2024-05-01T11:00:00Z", "time_spent": 1800, "merge_request_id": 20},
    ]
    issues = [{"id": 10, "state": "closed", "project_id": 1}]
    mrs = [{"id": 20, "state": "merged", "project_id": 1}]

    totals, categorized, f_issues, f_mrs, timestamps = aggregate_daily_time_categorized(timelogs, issues, mrs)

    assert totals["2024-05-01"] == 5400
    assert categorized["2024-05-01"]["issues_closed"] == 3600
    assert categorized["2024-05-01"]["mrs_merged"] == 1800
    assert f_issues[10] == 3600
    assert f_mrs[20] == 1800


def test_build_daily_time_from_time_stats():
    from internship_activity_tracker.infrastructure.gitlab.timelogs import build_daily_time_from_time_stats

    mock_client = MagicMock()
    issues = [
        {
            "id": 1,
            "project_id": 101,
            "iid": 1,
            "closed_at": "2024-05-01T10:00:00Z",
            "state": "closed",
            "time_stats": {"total_time_spent": 3600},
        }
    ]
    # formal_total is 0, so should add all 3600
    totals, categorized = build_daily_time_from_time_stats(issues, [], mock_client, "2024-05-01", "2024-05-01")

    assert totals["2024-05-01"] == 3600
    assert categorized["2024-05-01"]["issues_closed"] == 3600


def test_fetch_user_timelogs_success():
    from internship_activity_tracker.infrastructure.gitlab.timelogs import fetch_user_timelogs

    mock_client = MagicMock()
    mock_client._get.side_effect = [
        [{"id": 123, "username": "testuser"}],  # /users
        [{"id": 1, "time_spent": 3600}],  # /timelogs
    ]
    logs = fetch_user_timelogs(mock_client, "testuser", date(2024, 5, 1), date(2024, 5, 2))
    assert len(logs) == 1
    assert logs[0]["time_spent"] == 3600


def test_fetch_user_timelogs_not_found():
    from internship_activity_tracker.infrastructure.gitlab.timelogs import fetch_user_timelogs

    mock_client = MagicMock()
    mock_client._get.return_value = []
    logs = fetch_user_timelogs(mock_client, "unknown", date(2024, 5, 1), date(2024, 5, 2))
    assert logs == []


@pytest.mark.asyncio
async def test_fetch_user_timelogs_from_projects_async_error_handling():
    from unittest.mock import AsyncMock

    from internship_activity_tracker.infrastructure.gitlab.timelogs import fetch_user_timelogs_from_projects_async

    mock_client = MagicMock()
    mock_client._async_get = AsyncMock()
    # Global fails, per-project fails
    mock_client._async_get.side_effect = Exception("Boom")

    projects = [{"id": 101}]
    logs = await fetch_user_timelogs_from_projects_async(mock_client, 123, projects, date(2024, 5, 1), date(2024, 5, 2))
    assert logs == []
