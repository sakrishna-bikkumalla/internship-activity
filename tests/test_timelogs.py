from datetime import date
from unittest.mock import MagicMock
import pytest
from gitlab_compliance_checker.infrastructure.gitlab.timelogs import (
    fetch_user_timelogs_from_projects,
    aggregate_daily_time,
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
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}], # Global
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}], # Project 1 (Duplicate)
        [{"id": 2, "time_spent": 1800, "spent_at": "2024-05-02"}], # Project 2
    ]
    
    projects = [{"id": 101}, {"id": 102}]
    logs = fetch_user_timelogs_from_projects(mock_client, 123, projects, date(2024, 5, 1), date(2024, 5, 2))
    
    assert len(logs) == 2
    assert {l["id"] for l in logs} == {1, 2}

@pytest.mark.asyncio
async def test_fetch_user_timelogs_from_projects_async():
    from unittest.mock import AsyncMock
    mock_client = MagicMock()
    mock_client._async_get = AsyncMock()
    # Mock global search
    mock_client._async_get.side_effect = [
        [{"id": 1, "time_spent": 3600, "spent_at": "2024-05-01"}], # Global
        [{"id": 2, "time_spent": 1800, "spent_at": "2024-05-02"}], # Project 1
        [{"id": 3, "time_spent": 900, "spent_at": "2024-05-02"}],  # Project 2
    ]
    
    projects = [{"id": 101}, {"id": 102}]
    from gitlab_compliance_checker.infrastructure.gitlab.timelogs import fetch_user_timelogs_from_projects_async
    logs = await fetch_user_timelogs_from_projects_async(mock_client, 123, projects, date(2024, 5, 1), date(2024, 5, 2))
    
    assert len(logs) == 3
    assert {l["id"] for l in logs} == {1, 2, 3}
