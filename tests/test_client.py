import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    import aiohttp
except ModuleNotFoundError:

    class ClientResponseError(Exception):
        def __init__(self, request_info=None, history=(), status=0, headers=None):
            self.request_info = request_info
            self.history = history
            self.status = status
            self.headers = headers or {}
            super().__init__(f"HTTP {status}")

    class ClientConnectorError(Exception):
        def __init__(self, conn, os_error):
            self.conn = conn
            self.os_error = os_error
            super().__init__(str(os_error))

    class ServerDisconnectedError(Exception):
        pass

    aiohttp = types.SimpleNamespace(
        ClientResponseError=ClientResponseError,
        ClientConnectorError=ClientConnectorError,
        ServerDisconnectedError=ServerDisconnectedError,
        TCPConnector=type("TCPConnector", (object,), {}),
        ClientSession=type("ClientSession", (object,), {}),
    )
    sys.modules["aiohttp"] = aiohttp

try:
    import gitlab
except ModuleNotFoundError:
    gitlab = types.SimpleNamespace(Gitlab=type("Gitlab", (object,), {}))
    sys.modules["gitlab"] = gitlab

from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient, safe_api_call_async

# ---------------- SAFE API CALL TESTS ----------------


@pytest.mark.asyncio
async def test_safe_api_call_success():
    """Returns result on success."""

    async def mock_func(x):
        return x * 2

    assert await safe_api_call_async(mock_func, 5) == 10


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_429_retry(mock_sleep):
    """Retries on 429 with backoff."""
    mock_func = AsyncMock()
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={"Retry-After": "1"},
    )
    mock_func.side_effect = [err_429, "success"]
    result = await safe_api_call_async(mock_func)
    assert result == "success"
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(5)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_429_max_retries(mock_sleep):
    """Raises exception after max retries for 429."""
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={},
    )
    mock_func = AsyncMock(side_effect=err_429)
    with pytest.raises(Exception, match="Max retries reached"):
        await safe_api_call_async(mock_func)


# ---------------- GITLAB CLIENT TESTS ----------------


def test_gitlab_client_init():
    client = GitLabClient("https://gitlab.com/", "token")
    assert client.base_url == "https://gitlab.com"
    assert client.api_base == "https://gitlab.com/api/v4"
    assert client.headers == {"PRIVATE-TOKEN": "token"}


@patch("gitlab_compliance_checker.infrastructure.gitlab.client.gitlab.Gitlab")
def test_gitlab_client_lazy_init(mock_gitlab):
    client = GitLabClient("http://test", "token")
    gl = client.client
    assert gl is not None
    mock_gitlab.assert_called_once()


@pytest.mark.asyncio
async def test_evaluate_single_mr_success():
    """Test _evaluate_single_mr with mocked API calls."""
    client = GitLabClient("http://test", "token")
    mr = {
        "project_id": 1,
        "iid": 1,
        "state": "merged",
        "title": "Test MR",
        "description": "Description",
        "author": {"id": 1},
        "created_at": "2024-01-01T00:00:00Z",
        "merged_at": "2024-01-02T00:00:00Z",
        "upvotes": 1,
    }
    with patch.object(client, "_async_request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = [{"message": "feat: test"}]
        uname, flags = await client._evaluate_single_mr(mr)
        assert uname == "unknown"
        assert "is_merged" in flags


@pytest.mark.asyncio
async def test_evaluate_single_issue_with_exception_in_stats():
    """Test exception handling in issue time stats."""
    client = GitLabClient("http://test", "token")
    issue = {
        "state": "closed",
        "title": "fix: title",
        "description": "Description",
        "labels": ["bug"],
        "milestone": {"id": 1},
        "time_stats": "invalid",
        "created_at": "2024-01-01T00:00:00Z",
        "closed_at": "2024-01-10T00:00:00Z",
    }
    uname, flags = await client._evaluate_single_issue(issue)
    assert "no_time" in flags
