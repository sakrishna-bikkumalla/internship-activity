"""
test_merge_requests.py
~~~~~~~~~~~~~~~~~~~~
Tests for GitLab Merge Request utilities and compliance analysis.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gitlab_utils import merge_requests

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
    """Should return empty stats if client is not initialized."""
    mock_client = MagicMock()
    mock_client.client = None
    stats, problematic = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")
    assert stats["Total MRs Evaluated"] == 0
    assert problematic == []


@patch("gitlab_utils.merge_requests.analyze_description")
def test_get_single_user_live_mr_compliance_full_flow(mock_analyze):
    """Test the full compliance logic with successful and failing markers."""
    mock_client = MagicMock()
    mock_project = MagicMock()
    mock_mr_cached = MagicMock()
    mock_mr_cached.author = {"name": "target_user"}
    mock_mr_cached.iid = 123

    mock_mr_full = MagicMock()
    mock_mr_full.title = "Test MR"
    mock_mr_full.state = "opened"
    mock_mr_full.description = "Some description"
    mock_mr_full.head_pipeline = {"status": "failed"}
    mock_mr_full.time_stats.return_value = {"total_time_spent": 0}
    mock_mr_full.references = {"full": None}
    mock_mr_full.changes.return_value = {"changes": [{"new_path": "src/main.py"}]}

    mock_client.client.projects.get.return_value = mock_project
    mock_project.mergerequests.list.return_value = [mock_mr_cached]
    mock_project.mergerequests.get.return_value = mock_mr_full

    mock_analyze.return_value = {"description_score": 5, "quality_label": "Good", "feedback": []}

    stats, problematic = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "target_user")

    assert stats["Total MRs Evaluated"] == 1
    assert stats["Failed Pipelines"] == 1
    assert stats["No Time Spent"] == 1
    assert stats["No Issues Linked"] == 1
    assert stats["No Unit Tests"] == 1
    assert len(problematic) == 1
    assert problematic[0]["No Unit Tests"] is True


def test_get_single_user_live_mr_compliance_edge_cases():
    """Test exceptions and missing attributes in compliance checks."""
    mock_client = MagicMock()
    mock_project = MagicMock()
    mock_mr_cached = MagicMock()
    mock_mr_cached.author = {"name": "user"}

    mock_mr_full = MagicMock()
    mock_mr_full.description = ""  # No description
    del mock_mr_full.head_pipeline  # Attribute missing
    mock_mr_full.time_stats.side_effect = Exception("error")
    mock_mr_full.references = None
    mock_mr_full.changes.side_effect = Exception("error")

    mock_client.client.projects.get.return_value = mock_project
    mock_project.mergerequests.list.return_value = [mock_mr_cached]
    mock_project.mergerequests.get.return_value = mock_mr_full

    stats, problematic = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")

    assert stats["No Description"] == 1
    assert stats["No Time Spent"] == 1
    assert stats["No Issues Linked"] == 1
    assert stats["No Unit Tests"] == 1


def test_get_single_user_live_mr_compliance_various_unit_tests():
    """Test unit test detection logic in changes."""
    mock_client = MagicMock()
    mock_project = MagicMock()
    mock_mr_cached = MagicMock()
    mock_mr_cached.author = {"name": "user"}
    mock_mr_full = MagicMock()

    mock_client.client.projects.get.return_value = mock_project
    mock_project.mergerequests.list.return_value = [mock_mr_cached]
    mock_project.mergerequests.get.return_value = mock_mr_full

    # Case 1: Has "spec" file
    mock_mr_full.changes.return_value = {"changes": [{"new_path": "tests/my_spec.rb"}]}
    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")
    assert stats["No Unit Tests"] == 0

    # Case 2: Has "test" file
    mock_mr_full.changes.return_value = {"changes": [{"new_path": "tests/test_api.py"}]}
    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "user")
    assert stats["No Unit Tests"] == 0


def test_get_user_mrs_closed_state():
    """Test 'closed' state in get_user_mrs."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [{"id": 1, "state": "closed", "created_at": "2024-01-01T00:00:00Z"}]
    _, stats = merge_requests.get_user_mrs(mock_client, user_id=1)
    assert stats["closed"] == 1


def test_get_single_user_live_mr_compliance_different_author():
    """MRs from other authors should be skipped."""
    mock_client = MagicMock()
    mock_project = MagicMock()
    mock_mr_other = MagicMock()
    mock_mr_other.author = {"name": "other_user"}

    mock_client.client.projects.get.return_value = mock_project
    mock_project.mergerequests.list.return_value = [mock_mr_other]

    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1], "target_user")
    assert stats["Total MRs Evaluated"] == 0


def test_get_single_user_live_mr_compliance_exceptions():
    """Trigger explicit exception blocks."""
    mock_client = MagicMock()
    mock_project = MagicMock()
    mock_mr_cached = MagicMock()
    mock_mr_cached.author = {"name": "user"}
    mock_mr_full = MagicMock()
    mock_mr_full.description = "Valid description"

    mock_client.client.projects.get.return_value = mock_project
    mock_project.mergerequests.list.return_value = [mock_mr_cached]
    mock_project.mergerequests.get.return_value = mock_mr_full

    # Trigger exception in references block (line 157)
    # A string doesn't have .get(), so this will raise AttributeError
    mock_mr_full.references = "not-a-dict"

    # Trigger outer exception (line 194) by making projects.get fail for the SECOND project
    mock_client.client.projects.get.side_effect = [mock_project, Exception("Outer error")]

    stats, _ = merge_requests.get_single_user_live_mr_compliance(mock_client, [1, 2], "user")
    assert stats["No Issues Linked"] >= 1
