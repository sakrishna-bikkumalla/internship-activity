from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from internship_activity_tracker.infrastructure.gitlab import batch

# ---------------- RESOLVE PROJECT PATHS TESTS ----------------


def test_resolve_project_paths():
    mock_client = MagicMock()

    # Mock return for one valid, one invalid, one exception
    def _side_effect(path):
        if "proj1" in path:
            return {"id": 10}
        if "proj2" in path:
            return None
        raise Exception("API Error")

    mock_client._get.side_effect = _side_effect

    ids, failed = batch.resolve_project_paths(mock_client, ["group/proj1", "group/proj2", "group/proj3", "  "])
    assert ids == [10]
    assert "group/proj2" in failed
    assert "group/proj3" in failed
    assert len(failed) == 2


# ---------------- PROCESS SINGLE USER TESTS ----------------


def test_process_single_user_empty():
    assert batch.process_single_user(MagicMock(), "  ") is None


@patch("internship_activity_tracker.infrastructure.gitlab.users.get_user_by_username_async", new_callable=AsyncMock)
def test_process_single_user_not_found(mock_get_user):
    mock_get_user.return_value = None
    res = batch.process_single_user(MagicMock(), "missing")
    assert res["status"] == "Not Found"


@patch("internship_activity_tracker.infrastructure.gitlab.users.get_user_by_username_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.projects.get_user_projects_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.groups.get_user_groups_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.merge_requests.get_user_mrs_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.issues.get_user_issues_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.commits.get_user_commits_async", new_callable=AsyncMock)
def test_process_single_user_success(mock_commits, mock_issues, mock_mrs, mock_groups, mock_projects, mock_users):
    mock_client = MagicMock()
    mock_client._gql = None  # disable GraphQL fast path so mocks are used
    mock_users.return_value = {"id": 1, "username": "user1"}
    mock_projects.return_value = {"personal": [], "contributed": [{"id": 100}], "all": [{"id": 100}]}
    mock_groups.return_value = []
    mock_mrs.return_value = ([], {})
    mock_issues.return_value = ([], {})
    mock_commits.return_value = ([], {100: 5}, {"total": 5})

    res = batch.process_single_user(mock_client, "user1")
    assert res["status"] == "Success"
    assert res["data"]["commits"] == []
    assert len(res["data"]["projects"]["contributed"]) == 1


@patch("internship_activity_tracker.infrastructure.gitlab.users.get_user_by_username_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.projects.get_user_projects_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.groups.get_user_groups_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.merge_requests.get_user_mrs_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.issues.get_user_issues_async", new_callable=AsyncMock)
@patch("internship_activity_tracker.infrastructure.gitlab.commits.get_user_commits_async", new_callable=AsyncMock)
def test_process_single_user_with_project_ids(
    mock_commits, mock_issues, mock_mrs, mock_groups, mock_projects, mock_users
):
    mock_client = MagicMock()
    mock_client._gql = None
    mock_client._async_get = AsyncMock(side_effect=[{"id": 50}, Exception("404")])
    mock_users.return_value = {"id": 1, "username": "user1"}
    mock_projects.return_value = {"all": [], "contributed": [], "personal": []}
    mock_groups.return_value = []
    mock_mrs.return_value = ([], {})
    mock_issues.return_value = ([], {})
    mock_commits.return_value = ([], {}, {})

    batch.process_single_user(mock_client, "user1", project_ids=[50, 60])

    # Verify that get_user_commits_async was called with project 50
    args = mock_commits.call_args.args
    assert any(p["id"] == 50 for p in args[2])


def test_process_single_user_exception():
    mock_client = MagicMock()
    mock_client._gql = None
    with patch(
        "internship_activity_tracker.infrastructure.gitlab.users.get_user_by_username_async",
        new_callable=AsyncMock,
        side_effect=Exception("Crash"),
    ):
        res = batch.process_single_user(mock_client, "user1")
    assert res["status"] == "Error"
    assert "Crash" in res["error"]


# ---------------- BATCH PROCESSING TESTS ----------------


@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user")
def test_process_batch_users(mock_single):
    mock_single.side_effect = [{"username": "u1", "status": "Success"}, Exception("Critical")]
    res = batch.process_batch_users(MagicMock(), ["u1", "u2"])
    assert len(res) == 2
    assert res[0]["status"] == "Success"
    assert res[1]["status"] == "Crash"


@pytest.mark.asyncio
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_async", new_callable=MagicMock)
async def test_process_batch_users_async(mock_single):
    mock_single.return_value = {"username": "u1", "status": "Success"}
    res = await batch.process_batch_users_async(MagicMock(), ["u1"])
    assert len(res) == 1
    assert res[0]["username"] == "u1"


@pytest.mark.asyncio
@patch("internship_activity_tracker.infrastructure.gitlab.batch.process_single_user_async", new_callable=MagicMock)
async def test_process_batch_users_async_error(mock_single):
    mock_single.side_effect = Exception("Async fail")
    res = await batch.process_batch_users_async(MagicMock(), ["u1"])
    assert len(res) == 1
    assert res[0]["status"] == "Crash"
