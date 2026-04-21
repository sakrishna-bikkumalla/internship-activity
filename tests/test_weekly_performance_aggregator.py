import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from gitlab_compliance_checker.services.weekly_performance import aggregator

def test_parse_ist_date():
    # UTC 20:00 -> IST 01:30 (+1 day)
    assert aggregator._parse_ist_date("2024-04-18T20:00:00Z") == "2024-04-19"
    # UTC 01:00 -> IST 06:30 (same day)
    assert aggregator._parse_ist_date("2024-04-19T01:00:00Z") == "2024-04-19"
    # Fallback
    assert aggregator._parse_ist_date("not-a-date") == "not-a-date"

def test_get_user_id_found():
    mock_client = MagicMock()
    mock_client._get.return_value = [{"username": "target", "id": 123}]
    assert aggregator._get_user_id(mock_client, "target") == 123

def test_get_user_id_not_found():
    mock_client = MagicMock()
    mock_client._get.return_value = []
    assert aggregator._get_user_id(mock_client, "none") is None

def test_fetch_mrs_by_date():
    mock_client = MagicMock()
    # Mock author MRs
    mock_client._get_paginated.side_effect = [
        [{"id": 1, "merged_at": "2024-04-15T10:00:00Z"}],  # Author
        [{"id": 1, "merged_at": "2024-04-15T10:00:00Z"}],  # Assignee (duplicate)
    ]
    start = date(2024, 4, 15)
    end = date(2024, 4, 19)
    counts = aggregator._fetch_mrs_by_date(mock_client, 1, start, end)
    assert counts == {"2024-04-15": 1}

def test_fetch_issues_by_date():
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [{"created_at": "2024-04-15T10:00:00Z"}]
    start = date(2024, 4, 15)
    end = date(2024, 4, 19)
    counts = aggregator._fetch_issues_by_date(mock_client, 1, start, end)
    assert counts == {"2024-04-15": 1}

@patch("gitlab_compliance_checker.infrastructure.gitlab.users.get_user_by_username")
@patch("gitlab_compliance_checker.infrastructure.gitlab.projects.get_user_projects")
@patch("gitlab_compliance_checker.infrastructure.gitlab.commits.get_user_commits")
def test_fetch_commits_by_date(mock_commits, mock_projs, mock_users):
    mock_client = MagicMock()
    mock_users.return_value = {"id": 1}
    mock_projs.return_value = {"all": [101]}
    mock_commits.return_value = ([{"date": "2024-04-15"}], None, None)
    
    start = date(2024, 4, 15)
    end = date(2024, 4, 19)
    counts = aggregator._fetch_commits_by_date(mock_client, 1, "user", start, end)
    assert counts == {"2024-04-15": 1}

@patch("gitlab_compliance_checker.infrastructure.gitlab.timelogs.fetch_user_timelogs")
@patch("gitlab_compliance_checker.services.weekly_performance.aggregator._get_user_id")
@patch("gitlab_compliance_checker.services.weekly_performance.aggregator._fetch_mrs_by_date")
@patch("gitlab_compliance_checker.services.weekly_performance.aggregator._fetch_issues_by_date")
@patch("gitlab_compliance_checker.services.weekly_performance.aggregator._fetch_commits_by_date")
def test_aggregate_intern_data(mock_commits, mock_issues, mock_mrs, mock_user_id, mock_timelogs):
    mock_client = MagicMock()
    mock_user_id.return_value = 123
    mock_timelogs.return_value = [{"time_spent": 3600, "date": "2024-04-15"}]
    mock_mrs.return_value = {"2024-04-15": 2}
    mock_issues.return_value = {"2024-04-16": 1}
    mock_commits.return_value = {"2024-04-15": 5}
    
    start = date(2024, 4, 15)
    end = date(2024, 4, 19)
    activity = aggregator.aggregate_intern_data(mock_client, "user", "uid", "Name", start, end)
    
    assert activity.intern_name == "Name"
    assert activity.daily_data["2024-04-15"]["gitlab"]["mrs"] == 2
    assert activity.daily_data["2024-04-15"]["gitlab"]["commits"] == 5
    assert activity.daily_data["2024-04-15"]["gitlab"]["time_spent_seconds"] == 3600
    assert activity.daily_data["2024-04-16"]["gitlab"]["issues"] == 1

def test_aggregate_batch_interns():
    mock_client = MagicMock()
    with patch("gitlab_compliance_checker.services.weekly_performance.aggregator.aggregate_intern_data") as mock_agg:
        mock_agg.return_value = MagicMock()
        rows = [{"full_name": "Test", "gitlab_username": "user", "corpus_uid": "uid"}]
        results = aggregator.aggregate_batch_interns(mock_client, rows, date(2024, 4, 15), date(2024, 4, 19))
        assert len(results) == 1
        assert mock_agg.called
