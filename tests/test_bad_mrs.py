import pytest
from unittest.mock import MagicMock
from gitlab_utils.async_bad_mrs import (
    BATCH_USERNAMES,
    _check_user_compliance,
    fetch_all_bad_mrs
)

def test_hardcoded_usernames_list():
    """Verify BATCH_USERNAMES contains all 34 required users."""
    assert len(BATCH_USERNAMES) == 34
    assert "prav2702" in BATCH_USERNAMES
    assert "Pavani_Pothuganti" in BATCH_USERNAMES

def test_check_user_compliance_no_client():
    """Verify behavior when client is not initialized."""
    client = MagicMock()
    client.client = None
    result = _check_user_compliance(client, "testuser")

    assert result["Username"] == "testuser"
    assert result["Closed MRs"] == 0
    assert "Total BAD MRs" not in result

def test_check_user_compliance_user_not_found():
    """Verify behavior when user is not found on GitLab."""
    client = MagicMock()
    client._get.return_value = []

    result = _check_user_compliance(client, "nonexistent")
    assert result["Username"] == "nonexistent"
    assert result["Closed MRs"] == 0

def test_check_user_compliance_result_structure():
    """Verify result dictionary contains all expected keys (and no Total BAD MRs)."""
    client = MagicMock()
    client._get.return_value = [{"id": 123}] # user found
    client._get_paginated.return_value = [] # no MRs

    result = _check_user_compliance(client, "testuser")

    expected_keys = [
        "Username",
        "Closed MRs",
        "No Description",
        "Improper Description",
        "No Issues Linked",
        "No Time Spent",
        "No Unit Tests",
        "Failed Pipeline",
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"

    assert "Total BAD MRs" not in result

def test_fetch_all_bad_mrs_empty_list():
    """Verify behavior with empty username list."""
    client = MagicMock()
    results = fetch_all_bad_mrs(client, [])
    assert results == []

def test_fetch_all_bad_mrs_completeness():
    """Verify every requested username appears in results."""
    client = MagicMock()
    client._get.return_value = [] # no users found

    test_users = ["user1", "user2", "user3"]
    results = fetch_all_bad_mrs(client, test_users)

    assert len(results) == 3
    result_names = {r["Username"] for r in results}
    assert result_names == set(test_users)
    for r in results:
        assert r["Closed MRs"] == 0
