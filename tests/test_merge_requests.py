"""
test_merge_requests.py
~~~~~~~~~~~~~~~~~~~~
Tests for GitLab Merge Request utilities and compliance analysis.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gitlab_compliance_checker.infrastructure.gitlab import merge_requests

# ---------------------------------------------------------------------------
# Tests for get_user_mrs
# ---------------------------------------------------------------------------


def test_get_user_mrs_stats_structure():
    """mr_stats dict returned by get_user_mrs must contain all required keys."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = []
    _, stats = merge_requests.get_user_mrs(mock_client, user_id=999)
    required = {"total", "merged", "closed", "opened", "pending"}
    assert required.issubset(stats.keys())


def test_get_user_mrs_empty_response():
    """Empty API response should return zero stats."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = []
    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)
    assert mrs_list == []
    assert stats["total"] == 0


def test_get_user_mrs_with_filters():
    """Test date and project filtering in get_user_mrs."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [
        {"id": 1, "project_id": 10, "state": "merged", "created_at": "2024-01-01T00:00:00Z"},
        {"id": 2, "project_id": 20, "state": "opened", "created_at": "2024-01-01T00:00:00Z"},
    ]

    # Test project filter (only project 10)
    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1, project_ids=[10])
    assert len(mrs_list) == 1
    assert stats["total"] == 1
    assert mrs_list[0]["project_id"] == 10

    # Test date filters (verify they are passed to _get_paginated)
    merge_requests.get_user_mrs(mock_client, user_id=1, since="2024-01-01", until="2024-01-02")
    args, kwargs = mock_client._get_paginated.call_args
    assert kwargs["params"]["created_after"] == "2024-01-01"
    assert kwargs["params"]["created_before"] == "2024-01-02"


def test_get_user_mrs_exception_in_subcall():
    """Verify that exceptions in fetch_and_add are caught silently."""
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = Exception("API error")
    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)
    assert mrs_list == []
    assert stats["total"] == 0


# ---------------------------------------------------------------------------
# Tests for get_single_user_live_mr_compliance
# ---------------------------------------------------------------------------


def test_get_single_user_live_mr_compliance_no_client():
    """Should return empty stats if client is not provided."""
    stats, problematic = merge_requests.get_single_user_live_mr_compliance(None, [1], "user")
    assert stats["Total MRs Evaluated"] == 0
    assert problematic == []


@patch("gitlab_compliance_checker.infrastructure.gitlab.merge_requests.analyze_description")
def test_get_single_user_live_mr_compliance_full_flow(mock_analyze, monkeypatch):
    """Test the full compliance logic with successful and failing markers."""
    # Undo the global mock from conftest.py
    monkeypatch.undo()

    mock_client = MagicMock()

    # Mock user resolution
    mock_client._get.return_value = [{"id": 123, "username": "target_user"}]

    # Mock MR list
    mr_dict = {
        "id": 1,
        "project_id": 1,
        "iid": 1,
        "title": "Test MR",
        "state": "opened",
        "description": "Some description",
    }
    mock_client._get_paginated.return_value = [mr_dict]

    # Mock evaluation results
    evaluation_flags = {
        "no_desc": False,
        "failed_pipe": True,
        "no_issues": True,
        "no_time": True,
        "no_unit_tests": True,
    }

    def mock_run_sync(coro):
        if hasattr(coro, "close"):
            coro.close()
        return [("target_user", evaluation_flags)]

    mock_client._run_sync.side_effect = mock_run_sync

    mock_analyze.return_value = {"description_score": 5, "quality_label": "Good", "feedback": []}

    stats, problematic = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "target_user")

    assert stats["Total MRs Evaluated"] == 1
    assert stats["Failed Pipelines"] == 1
    assert stats["No Time Spent"] == 1
    assert stats["No Issues Linked"] == 1
    assert stats["No Unit Tests"] == 1
    assert len(problematic) == 1
    assert problematic[0]["No Unit Tests"] is True


def test_get_single_user_live_mr_compliance_edge_cases(monkeypatch):
    """Test exceptions and missing attributes in compliance checks."""
    monkeypatch.undo()
    mock_client = MagicMock()
    mock_client._get.return_value = [{"id": 123, "username": "user"}]

    mr_dict = {
        "id": 1,
        "project_id": 1,
        "iid": 1,
        "description": "",
    }
    mock_client._get_paginated.return_value = [mr_dict]

    evaluation_flags = {
        "no_desc": True,
        "failed_pipe": False,
        "no_issues": True,
        "no_time": True,
        "no_unit_tests": True,
    }

    def mock_run_sync(coro):
        if hasattr(coro, "close"):
            coro.close()
        return [("user", evaluation_flags)]

    mock_client._run_sync.side_effect = mock_run_sync

    stats, problematic = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")

    assert stats["No Description"] == 1
    assert stats["No Time Spent"] == 1
    assert stats["No Issues Linked"] == 1
    assert stats["No Unit Tests"] == 1


def test_get_user_mrs_closed_state():
    """Test 'closed' state in get_user_mrs."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [{"id": 1, "state": "closed", "created_at": "2024-01-01T00:00:00Z"}]
    _, stats = merge_requests.get_user_mrs(mock_client, user_id=1)
    assert stats["closed"] == 1


def test_get_single_user_live_mr_compliance_different_author(monkeypatch):
    """MRs from other authors should be skipped (handled by API filter in new version)."""
    monkeypatch.undo()
    mock_client = MagicMock()
    # Mock user resolution
    mock_client._get.return_value = [{"id": 123, "username": "target_user"}]
    # API returns nothing for this author
    mock_client._get_paginated.return_value = []

    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "target_user")
    assert stats["Total MRs Evaluated"] == 0


def test_get_single_user_live_mr_compliance_exceptions(monkeypatch):
    """Trigger explicit exception blocks."""
    monkeypatch.undo()
    mock_client = MagicMock()
    mock_client._get.return_value = [{"id": 123, "username": "user"}]

    mr_dict = {
        "id": 1,
        "project_id": 1,
        "iid": 1,
        "description": "Valid description",
    }
    mock_client._get_paginated.return_value = [mr_dict]

    # Trigger exception by returning something that ZIP logic can't handle well or evaluate_all fails
    def mock_run_sync_error(coro):
        if hasattr(coro, "close"):
            coro.close()
        raise Exception("Eval error")

    mock_client._run_sync.side_effect = mock_run_sync_error

    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")
    # Should handle exception gracefully
    assert stats["Total MRs Evaluated"] == 0
