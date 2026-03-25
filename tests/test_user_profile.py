"""
test_user_profile.py
~~~~~~~~~~~~~~~~~~~~
Tests for User Profile MR data structures and graceful edge-case handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from gitlab_utils import merge_requests

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_user_mrs_stats_structure():
    """mr_stats dict returned by get_user_mrs must contain all required keys."""
    mock_client = MagicMock()
    # No MRs returned — simulate empty API response
    mock_client._get_paginated.return_value = []

    _, stats = merge_requests.get_user_mrs(mock_client, user_id=999)

    required = {"total", "merged", "closed", "opened", "pending"}
    assert required.issubset(stats.keys()), f"Missing keys: {required - stats.keys()}"


def test_get_user_mrs_empty_response():
    """Empty API response should return zero stats and empty MR list."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = []

    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)

    assert mrs_list == []
    assert stats["total"] == 0
    assert stats["merged"] == 0
    assert stats["opened"] == 0
    assert stats["closed"] == 0


def test_get_user_mrs_counts_states_correctly():
    """MR state counts should be tallied correctly from API response items."""
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [
        {
            "id": 1,
            "title": "MR1",
            "state": "merged",
            "project_id": 10,
            "web_url": "",
            "created_at": "",
            "description": "desc",
        },
        {
            "id": 2,
            "title": "MR2",
            "state": "opened",
            "project_id": 10,
            "web_url": "",
            "created_at": "",
            "description": "desc",
        },
        {
            "id": 3,
            "title": "MR3",
            "state": "opened",
            "project_id": 10,
            "web_url": "",
            "created_at": "",
            "description": "desc",
        },
        {
            "id": 4,
            "title": "MR4",
            "state": "closed",
            "project_id": 10,
            "web_url": "",
            "created_at": "",
            "description": "desc",
        },
    ]

    # Simulate: author call returns MRs, assignee call returns nothing
    call_count = {"n": 0}

    def paginated_side_effect(*args, **kwargs):
        if call_count["n"] == 0:
            call_count["n"] += 1
            return mock_client._get_paginated.return_value
        return []

    mock_client._get_paginated.side_effect = paginated_side_effect

    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)

    assert stats["total"] == 4
    assert stats["merged"] == 1
    assert stats["opened"] == 2
    assert stats["closed"] == 1


def test_get_user_mrs_deduplicates_by_id():
    """The same MR appearing in author + assignee responses should be counted once."""
    mock_client = MagicMock()

    duplicate_mr = {
        "id": 99,
        "title": "Dup MR",
        "state": "merged",
        "project_id": 1,
        "web_url": "",
        "created_at": "",
        "description": "x",
    }

    # Both author and assignee queries return the same MR
    mock_client._get_paginated.return_value = [duplicate_mr]

    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)

    assert stats["total"] == 1  # counted only once
    assert len(mrs_list) == 1


def test_get_user_mrs_api_exception_handled():
    """get_user_mrs should return empty results if the API call raises."""
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = Exception("Network error")

    mrs_list, stats = merge_requests.get_user_mrs(mock_client, user_id=1)

    assert mrs_list == []
    assert stats["total"] == 0
