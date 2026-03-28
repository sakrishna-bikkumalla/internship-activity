import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gitlab_utils import async_bad_mrs

# ---------------- FETCH JSON TESTS ----------------


@pytest.mark.asyncio
async def test_fetch_json_success():
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {"key": "val"}
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    sem = asyncio.Semaphore(1)
    res = await async_bad_mrs.fetch_json(mock_session, "http://test", sem)
    assert res == {"key": "val"}


@pytest.mark.asyncio
async def test_fetch_json_429_retry():
    mock_session = MagicMock()
    mock_resp_429 = AsyncMock()
    mock_resp_429.status = 429
    mock_resp_429.headers = {"Retry-After": "1"}

    mock_resp_200 = AsyncMock()
    mock_resp_200.status = 200
    mock_resp_200.json.return_value = {"ok": True}

    cm_429 = AsyncMock()
    cm_429.__aenter__.return_value = mock_resp_429
    cm_200 = AsyncMock()
    cm_200.__aenter__.return_value = mock_resp_200
    mock_session.get.side_effect = [cm_429, cm_200]

    sem = asyncio.Semaphore(1)
    with patch("asyncio.sleep", return_value=None):
        res = await async_bad_mrs.fetch_json(mock_session, "http://test", sem)
    assert res == {"ok": True}


@pytest.mark.asyncio
async def test_fetch_json_429_large_retry():
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.headers = {"Retry-After": "120"}
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    sem = asyncio.Semaphore(1)
    with pytest.raises(Exception, match="Please try again after 120 seconds"):
        await async_bad_mrs.fetch_json(mock_session, "http://test", sem)


@pytest.mark.asyncio
async def test_fetch_json_fail_eventually():
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network error")
    sem = asyncio.Semaphore(1)
    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(Exception, match="Network error"):
            await async_bad_mrs.fetch_json(mock_session, "http://test", sem)


# ---------------- EVALUATE SINGLE MR TESTS ----------------


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.analyze_description")
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_full_markers(mock_fetch, mock_analyze):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)

    mr = {
        "project_id": 1,
        "iid": 1,
        "state": "merged",
        "title": "Short title",
        "description": "Short desc",
        "author": {"id": 10},
        "upvotes": 0,
        "created_at": "2024-01-01T00:00:00Z",
        "merged_at": "2024-01-10T00:00:00Z",  # > 1 week
        "_username": "user1",
    }

    mock_analyze.return_value = {"quality_label": "Low"}
    # Mock fetches for commits, notes, issues, changes
    mock_fetch.side_effect = [
        [{"message": "non-semantic"}],  # commits
        [],  # notes (internal review)
        [],  # issues
        {"changes": []},  # changes (unit tests)
    ]

    uname, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "http://gl", {}, mr)

    assert uname == "user1"
    assert flags["improper_desc"] is True
    assert flags["no_semantic_commits"] is True
    assert flags["no_internal_review"] is True
    assert flags["no_issues"] is True
    assert flags["no_unit_tests"] is True
    assert flags["merge_gt_1_week"] is True


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_rejected_pipeline(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)
    mr = {"project_id": 1, "iid": 1, "state": "closed", "_username": "u1", "created_at": "2024-01-01T00:00:00Z"}
    # Mock pipeline fetch for rejected MR
    mock_fetch.side_effect = [
        [{"status": "failed"}],  # Pipelines
        [],  # Commits (fallback to title)
        [],  # Notes
        [],  # Issues
        [],  # Changes
    ]

    uname, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "http://gl", {}, mr)
    assert flags["failed_pipe"] is True
    assert flags["is_closed_rejected"] is True


# ---------------- FETCH USER MRS TESTS ----------------


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_fetch_user_mrs(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)

    # 1. User lookup
    mock_fetch.side_effect = [
        [{"id": 1, "username": "User1"}],  # Exact match
        [{"id": 101, "project_id": 1, "iid": 1}],  # MRs
    ]

    mrs = await async_bad_mrs._fetch_user_mrs(mock_session, sem, "http://gl", {}, "user1")
    assert len(mrs) == 1
    assert mrs[0]["_username"] == "user1"


# ---------------- INTEGRATION TESTS ----------------


def test_fetch_all_bad_mrs_wrapper():
    mock_client = MagicMock()
    mock_client.base_url = "http://gl"
    mock_client.headers = {}

    # Mock the internal async calls
    with patch("gitlab_utils.async_bad_mrs._run_batch", return_value=[{"Username": "u1"}]):
        res = async_bad_mrs.fetch_all_bad_mrs(mock_client, ["u1"])
        assert res[0]["Username"] == "u1"


# ---------------- ADDITIONAL EXTENDED TESTS ----------------


@pytest.mark.asyncio
async def test_fetch_json_429_no_retry_after():
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.headers = {}
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    sem = asyncio.Semaphore(1)
    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(Exception, match="Max retries reached"):
            await async_bad_mrs.fetch_json(mock_session, "http://test", sem)


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
@patch("gitlab_utils.async_bad_mrs.analyze_description")
async def test_evaluate_single_mr_analyze_description_exception(mock_analyze, mock_fetch):
    mock_analyze.side_effect = Exception("Analyze fail")
    mock_fetch.return_value = []
    mr = {"project_id": 1, "iid": 1, "_username": "u1", "description": "desc"}
    _, flags = await async_bad_mrs._evaluate_single_mr(AsyncMock(), asyncio.Semaphore(1), "h", {}, mr)
    # Exception is caught, improper_desc remains False (default)
    assert flags["improper_desc"] is False


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_rate_limits(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)
    mr = {"project_id": 1, "iid": 1, "state": "closed", "_username": "u1"}

    # 1. Pipeline Rate Limit
    mock_fetch.side_effect = Exception("Rate Limit Exceeded")
    with pytest.raises(Exception, match="Rate Limit Exceeded"):
        await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)

    # 2. Commits Rate Limit
    mr["state"] = "merged"
    mock_fetch.side_effect = Exception("Rate Limit Exceeded")
    with pytest.raises(Exception, match="Rate Limit Exceeded"):
        await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)

    # 3. Notes Rate Limit
    mock_fetch.side_effect = [[], Exception("Rate Limit Exceeded")]
    with pytest.raises(Exception, match="Rate Limit Exceeded"):
        await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_time_tracking_misc(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)

    # Merge > 2 days, < 1 week
    mr = {
        "project_id": 1,
        "iid": 1,
        "state": "merged",
        "_username": "u1",
        "created_at": "2024-01-01T00:00:00Z",
        "merged_at": "2024-01-04T00:00:00Z",  # 3 days
        "time_stats": {"total_time_spent": 0},  # Trigger lines 174-176
    }
    mock_fetch.return_value = []
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["merge_gt_2_days"] is True
    assert flags["merge_gt_1_week"] is False
    assert flags["no_time"] is True

    # Closed MR time tracking
    mr["state"] = "closed"
    mr["merged_at"] = None
    mr["closed_at"] = "2024-01-10T00:00:00Z"
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["merge_gt_1_week"] is True

    # Open MR (fallback to now)
    mr["state"] = "opened"
    mr["merged_at"] = None
    mr["closed_at"] = None
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    # If it's now vs 2024, it's definitely > 1 week
    assert flags["merge_gt_1_week"] is True


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_fallbacks(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)
    mr = {"project_id": 1, "iid": 1, "state": "merged", "_username": "u1", "title": "feat: init", "upvotes": 1}

    # Issues fallback (regex fails)
    # Unit tests fallback (title fails)
    # Upvotes review
    mock_fetch.side_effect = [
        [{"message": "feat: init"}],  # commits
        [],  # notes (upvotes will cover)
        [],  # issues fallback
        {"changes": [{"new_path": "tests/test.py"}]},  # changes fallback
    ]
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["no_internal_review"] is False
    assert flags["no_issues"] is True
    assert flags["no_unit_tests"] is False


# ---------------- EVEN MORE EXTENDED TESTS ----------------


@pytest.mark.asyncio
async def test_fetch_json_edge_cases():
    mock_session = MagicMock()
    sem = asyncio.Semaphore(1)

    # 1. ValueError in Retry-After
    mock_resp_429 = AsyncMock()
    mock_resp_429.status = 429
    mock_resp_429.headers = {"Retry-After": "abc"}
    mock_resp_200 = AsyncMock()
    mock_resp_200.status = 200
    mock_resp_200.json.return_value = {"ok": True}
    mock_session.get.side_effect = [
        AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_429)),
        AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_200)),
    ]
    with patch("asyncio.sleep", return_value=None):
        res = await async_bad_mrs.fetch_json(mock_session, "http://test", sem)
    assert res == {"ok": True}

    # 2. 204 Status
    mock_resp_204 = AsyncMock()
    mock_resp_204.status = 204
    mock_session.get.side_effect = [AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_204))]
    res = await async_bad_mrs.fetch_json(mock_session, "http://test", sem)
    assert res is None

    # 3. Final return None
    mock_resp_500 = AsyncMock()
    mock_resp_500.status = 500
    mock_session.get.side_effect = [AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_500))]
    res = await async_bad_mrs.fetch_json(mock_session, "http://test", sem)
    assert res is None


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_evaluate_single_mr_more_branch_coverage(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)

    # Pipeline status failed (embedded)
    mr = {"project_id": 1, "iid": 1, "state": "merged", "_username": "u1", "pipeline": {"status": "failed"}}
    mock_fetch.return_value = []
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["failed_pipe"] is True

    # Internal Review - Author match, System note loop check
    mr = {"project_id": 1, "iid": 1, "state": "merged", "_username": "u1", "author": {"id": 10}, "upvotes": 0}
    mock_fetch.side_effect = [
        [],  # commits
        [
            {"system": True, "author": {"id": 20}},
            {"system": False, "author": {"id": 10}},  # Same author
            {"system": False, "author": {"id": 30}},  # Other human!
        ],
        [],  # issues
        [],  # changes
    ]
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["no_internal_review"] is False

    # Regex matches
    mr["title"] = "#123 feature"
    mr["title_lower"] = "#123 feature"
    mr["description"] = "spec"
    mock_fetch.side_effect = [
        [],  # commits
        [],  # notes
    ]
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    assert flags["no_issues"] is False
    assert flags["no_unit_tests"] is False

    # Exception in time tracking (bad date)
    mr["created_at"] = "invalid-date"
    _, flags = await async_bad_mrs._evaluate_single_mr(mock_session, sem, "h", {}, mr)
    # Just verify it doesn't crash


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs.fetch_json")
async def test_fetch_user_mrs_ids(mock_fetch):
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)
    mock_fetch.side_effect = [[{"id": 1, "username": "user1"}], []]
    # Coverage for project_id and group_id params
    await async_bad_mrs._fetch_user_mrs(mock_session, sem, "h", {}, "user1", project_id="p1", group_id="g1")
    params = mock_fetch.call_args_list[1].kwargs["params"]
    assert params["project_id"] == "p1"
    assert params["group_id"] == "g1"


@pytest.mark.asyncio
@patch("gitlab_utils.async_bad_mrs._fetch_user_mrs")
@patch("gitlab_utils.async_bad_mrs._evaluate_single_mr")
async def test_run_batch_full(mock_eval, mock_fetch):
    client = MagicMock(base_url="http://gl", headers={})
    mock_fetch.return_value = [{"iid": 1, "project_id": 1, "_username": "u1"}]
    mock_eval.return_value = (
        "u1",
        {
            "is_closed_rejected": True,
            "failed_pipe": True,
            "no_desc": True,
            "improper_desc": True,
            "no_issues": True,
            "no_time": True,
            "no_unit_tests": True,
            "no_semantic_commits": True,
            "no_internal_review": True,
            "merge_gt_1_week": True,
            "merge_gt_2_days": True,
        },
    )

    res = await async_bad_mrs._run_batch(client, ["u1"])
    assert len(res) == 1
    row = res[0]
    assert row["Closed MRs"] == 1
    assert row["Failed Pipeline"] == 1
    assert row["No Desc"] == 1
    assert row["No Semantic Commits"] == 1


def test_fetch_all_bad_mrs_runtime_error():
    mock_client = MagicMock(base_url="http://gl", headers={})
    # Patch nest_asyncio.apply to prevent it from overriding our mock
    with patch("nest_asyncio.apply"):
        with patch("gitlab_utils.async_bad_mrs.asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no loop")
            with patch("gitlab_utils.async_bad_mrs.asyncio.new_event_loop") as mock_new:
                mock_loop = MagicMock()
                mock_new.return_value = mock_loop
                with patch("gitlab_utils.async_bad_mrs.asyncio.set_event_loop"):
                    with patch("gitlab_utils.async_bad_mrs._run_batch", new_callable=MagicMock) as mock_run:
                        mock_run.return_value = []
                        async_bad_mrs.fetch_all_bad_mrs(mock_client, ["u1"])
                        mock_get.assert_called()
                        mock_new.assert_called_once()
                        mock_loop.run_until_complete.assert_called_once()
