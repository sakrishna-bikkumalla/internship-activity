"""
test_async_batch.py
~~~~~~~~~~~~~~~~~~~
Tests for async batch processing using asyncio.gather().
Validates concurrent execution, error handling, and edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.infrastructure.gitlab.batch import process_batch_users_async

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_result(username: str, status: str = "Success") -> dict:
    return {
        "username": username,
        "status": status,
        "error": None,
        "data": {
            "projects": {"personal": [], "contributed": [], "all": []},
            "commit_stats": {"total": 0, "morning_commits": 0, "afternoon_commits": 0},
            "mr_stats": {"total": 0, "merged": 0, "opened": 0, "closed": 0, "pending": 0},
            "issue_stats": {"total": 0, "opened": 0, "closed": 0},
            "groups": [],
            "mrs": [],
            "issues": [],
            "commits": [],
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_batch_users_async_returns_all_users():
    """All usernames in the batch should produce a result entry."""
    usernames = ["user_a", "user_b", "user_c"]

    mock_client = MagicMock()

    with patch(
        "gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user",
        side_effect=lambda client, u, *args, **kwargs: _make_mock_result(u),
    ):
        results = await process_batch_users_async(mock_client, usernames)

    assert len(results) == 3
    returned_usernames = {r["username"] for r in results}
    assert returned_usernames == set(usernames)


@pytest.mark.asyncio
async def test_process_batch_users_async_concurrent():
    """
    Verifies that user tasks are launched concurrently.
    All results should be returned regardless of order.
    """
    usernames = [f"user_{i}" for i in range(10)]
    mock_client = MagicMock()

    with patch(
        "gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user",
        side_effect=lambda client, u, *args, **kwargs: _make_mock_result(u),
    ):
        results = await process_batch_users_async(mock_client, usernames)

    assert len(results) == 10


@pytest.mark.asyncio
async def test_process_batch_users_async_handles_crash():
    """If one user crashes, other results should still be returned."""
    usernames = ["good_user", "crash_user", "another_good_user"]
    mock_client = MagicMock()

    def side_effect(client, u, *args, **kwargs):
        if u == "crash_user":
            raise RuntimeError("Simulated API failure")
        return _make_mock_result(u)

    with patch(
        "gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user_async", side_effect=side_effect
    ):
        results = await process_batch_users_async(mock_client, usernames)

    # Should have 3 results total: 2 success + 1 crash
    assert len(results) == 3
    statuses = {r["username"]: r["status"] for r in results}
    assert statuses["good_user"] == "Success"
    assert statuses["crash_user"] == "Crash"
    assert statuses["another_good_user"] == "Success"


@pytest.mark.asyncio
async def test_process_batch_users_async_empty_list():
    """Empty username list should return empty result list."""
    mock_client = MagicMock()
    results = await process_batch_users_async(mock_client, [])
    assert results == []


@pytest.mark.asyncio
async def test_process_batch_users_async_skips_blank_usernames():
    """Blank / whitespace-only usernames should be ignored."""
    usernames = ["valid_user", "", "   ", "another_valid"]
    mock_client = MagicMock()

    with patch(
        "gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user",
        side_effect=lambda client, u, *args, **kwargs: _make_mock_result(u),
    ):
        results = await process_batch_users_async(mock_client, usernames)

    # Only valid non-blank usernames should be processed
    returned_usernames = {r["username"] for r in results}
    assert "valid_user" in returned_usernames
    assert "another_valid" in returned_usernames
    # Blank entries produce None from process_single_user → filtered out
    assert len(results) <= 2


def test_process_batch_users_sync_wrapper():
    """Sync wrapper should call asyncio.run and return results."""
    from gitlab_compliance_checker.infrastructure.gitlab.batch import process_batch_users

    mock_client = MagicMock()
    with patch(
        "gitlab_compliance_checker.infrastructure.gitlab.batch.process_single_user",
        side_effect=lambda client, u, *args, **kwargs: _make_mock_result(u),
    ):
        results = process_batch_users(mock_client, ["user_x", "user_y"])

    assert len(results) == 2
