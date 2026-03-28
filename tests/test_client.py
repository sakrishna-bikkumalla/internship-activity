from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from gitlab_utils.client import GitLabClient, safe_api_call_async

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

    # 1. 429 response
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={"Retry-After": "1"},
    )

    # Fail once, then succeed
    mock_func.side_effect = [err_429, "success"]

    result = await safe_api_call_async(mock_func)
    assert result == "success"
    assert mock_sleep.call_count == 1
    # First retry backoff: 5 * (0 + 1) = 5
    mock_sleep.assert_called_with(5)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_429_max_retries(mock_sleep):
    """Raises exception after max retries for 429."""
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={},  # Must be a dict to avoid .get() failure
    )

    mock_func = AsyncMock(side_effect=err_429)

    with pytest.raises(Exception, match="Max retries reached"):
        await safe_api_call_async(mock_func)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_429_large_retry_after(mock_sleep):
    """Raises immediate exception if Retry-After > 60."""
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={"Retry-After": "120"},  # Too long
    )

    mock_func = AsyncMock(side_effect=err_429)

    with pytest.raises(Exception, match="Please try again after 120 seconds"):
        await safe_api_call_async(mock_func)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_429_invalid_retry_after(mock_sleep):
    """Gracefully handles non-integer Retry-After."""
    err_429 = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"),
        history=(),
        status=429,
        headers={"Retry-After": "soon"},
    )

    # Fail once then success
    mock_func = AsyncMock(side_effect=[err_429, "ok"])
    assert await safe_api_call_async(mock_func) == "ok"


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_connection_error(mock_sleep):
    """Retries on ConnectionError."""
    mock_func = AsyncMock(side_effect=[aiohttp.ClientConnectorError(MagicMock(), MagicMock()), "ok"])
    assert await safe_api_call_async(mock_func) == "ok"
    # Connection backoff: 5 * (0 + 1) = 5
    mock_sleep.assert_called_with(5)


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_safe_api_call_generic_exception(mock_sleep):
    """Retries on generic Exception and returns [] at last."""
    mock_func = AsyncMock(side_effect=Exception("random"))
    assert await safe_api_call_async(mock_func) == []
    assert mock_sleep.call_count == 4  # max_retries - 1


# ---------------- GITLAB CLIENT TESTS ----------------


def test_gitlab_client_init():
    client = GitLabClient("https://gitlab.com/", "token")
    assert client.base_url == "https://gitlab.com"
    assert client.api_base == "https://gitlab.com/api/v4"
    assert client.headers == {"PRIVATE-TOKEN": "token"}


@patch("gitlab_utils.client.gitlab.Gitlab")
@patch("gitlab_utils.client.st.sidebar")
def test_gitlab_client_lazy_init(mock_sidebar, mock_gitlab):
    client = GitLabClient("http://test", "token")
    # First access
    gl = client.client
    assert gl is not None
    mock_gitlab.assert_called_once()
    assert mock_sidebar.write.call_count >= 1


@patch("gitlab_utils.client.gitlab.Gitlab")
@patch("gitlab_utils.client.st.sidebar")
def test_gitlab_client_lazy_init_failure(mock_sidebar, mock_gitlab):
    mock_gitlab.side_effect = Exception("Auth failed")
    client = GitLabClient("http://test", "token")
    gl = client.client
    assert gl is None
    assert client.error_msg == "Auth failed"


@pytest.mark.asyncio
@patch("gitlab_utils.client.GitLabClient._get_session")
async def test_gitlab_client_request_204(mock_get_session):
    """204 No Content should return None."""
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 204
    mock_response.raise_for_status = MagicMock()
    # session.request() returns an async context manager
    mock_session.request.return_value.__aenter__.return_value = mock_response
    mock_get_session.return_value = mock_session

    client = GitLabClient("http://test", "token")
    res = client._request("GET", "/test")
    assert res is None


@patch("gitlab_utils.client.GitLabClient._get")
def test_gitlab_client_get_paginated(mock_get):
    client = GitLabClient("http://test", "token")

    # 2 pages of data
    mock_get.side_effect = [[{"id": 1}, {"id": 2}], [{"id": 3}], []]

    # per_page = 2
    res = client._get_paginated("/test", per_page=2, max_pages=5)
    assert len(res) == 3
    assert res[0]["id"] == 1
    assert res[2]["id"] == 3
    assert mock_get.call_count == 2  # Stopped because page 2 had < 2 items


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("gitlab_utils.client.GitLabClient._get_session")
async def test_gitlab_client_request_500_retry_and_fallback(mock_get_session, mock_sleep):
    """Retries on 500 and eventually returns []."""
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        request_info=MagicMock(url="http://test"), history=(), status=500
    )
    mock_session.request.return_value.__aenter__.return_value = mock_response
    mock_get_session.return_value = mock_session

    client = GitLabClient("http://test", "token")
    res = client._request("GET", "/test")
    # safe_api_call_async returns [] on generic Exception or ClientResponseError after retries
    assert res == []
    assert mock_sleep.call_count == 4


@pytest.mark.asyncio
@patch("gitlab_utils.client.GitLabClient._get_session")
async def test_gitlab_client_request_json(mock_get_session):
    """Normal response should return JSON."""
    mock_session = MagicMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"key": "val"}
    mock_session.request.return_value.__aenter__.return_value = mock_response
    mock_get_session.return_value = mock_session

    client = GitLabClient("http://test", "token")
    res = client._get("/test")
    assert res == {"key": "val"}


@patch("gitlab_utils.client.GitLabClient._get")
def test_gitlab_client_get_paginated_empty_break(mock_get):
    """Breaks early if batch is empty."""
    client = GitLabClient("http://test", "token")
    mock_get.return_value = []
    res = client._get_paginated("/test")
    assert res == []
    assert mock_get.call_count == 1
