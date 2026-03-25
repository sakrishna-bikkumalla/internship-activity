import pytest
import requests
from unittest.mock import MagicMock, patch, PropertyMock
from gitlab_utils.client import safe_api_call, GitLabClient

# ---------------- SAFE API CALL TESTS ----------------

def test_safe_api_call_success():
    """Returns result on success."""
    assert safe_api_call(lambda x: x * 2, 5) == 10

@patch("time.sleep")
def test_safe_api_call_429_retry(mock_sleep):
    """Retries on 429 with backoff."""
    mock_func = MagicMock()

    # 1. 429 response
    response_429 = MagicMock()
    response_429.status_code = 429
    response_429.headers = {"Retry-After": "1"}
    err_429 = requests.exceptions.HTTPError(response=response_429)
    err_429.request = MagicMock(url="http://test")

    # Fail once, then succeed
    mock_func.side_effect = [err_429, "success"]

    result = safe_api_call(mock_func)
    assert result == "success"
    assert mock_sleep.call_count == 1
    # First retry backoff: 5 * (0 + 1) = 5
    mock_sleep.assert_called_with(5)

@patch("time.sleep")
def test_safe_api_call_429_max_retries(mock_sleep):
    """Raises exception after max retries for 429."""
    response_429 = MagicMock()
    response_429.status_code = 429
    err_429 = requests.exceptions.HTTPError(response=response_429)
    err_429.request = MagicMock(url="http://test")

    mock_func = MagicMock(side_effect=err_429)

    with pytest.raises(Exception, match="Max retries reached"):
        safe_api_call(mock_func)

@patch("time.sleep")
def test_safe_api_call_429_large_retry_after(mock_sleep):
    """Raises immediate exception if Retry-After > 60."""
    response_429 = MagicMock()
    response_429.status_code = 429
    response_429.headers = {"Retry-After": "120"} # Too long
    err_429 = requests.exceptions.HTTPError(response=response_429)
    err_429.request = MagicMock(url="http://test")

    mock_func = MagicMock(side_effect=err_429)

    with pytest.raises(Exception, match="Please try again after 120 seconds"):
        safe_api_call(mock_func)

@patch("time.sleep")
def test_safe_api_call_429_invalid_retry_after(mock_sleep):
    """Gracefully handles non-integer Retry-After."""
    response_429 = MagicMock()
    response_429.status_code = 429
    response_429.headers = {"Retry-After": "soon"}
    err_429 = requests.exceptions.HTTPError(response=response_429)
    err_429.request = MagicMock(url="http://test")

    # Fail once then success
    mock_func = MagicMock(side_effect=[err_429, "ok"])
    assert safe_api_call(mock_func) == "ok"

@patch("time.sleep")
def test_safe_api_call_connection_error(mock_sleep):
    """Retries on ConnectionError."""
    mock_func = MagicMock(side_effect=[requests.exceptions.ConnectionError("reset"), "ok"])
    assert safe_api_call(mock_func) == "ok"
    # Connection backoff: 5 * (0 + 1) = 5
    mock_sleep.assert_called_with(5)

@patch("time.sleep")
def test_safe_api_call_generic_exception(mock_sleep):
    """Retries on generic Exception and returns [] at last."""
    mock_func = MagicMock(side_effect=Exception("random"))
    assert safe_api_call(mock_func) == []
    assert mock_sleep.call_count == 4 # max_retries - 1

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

@patch("gitlab_utils.client._SESSION")
def test_gitlab_client_request_204(mock_session):
    """204 No Content should return None."""
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_session.request.return_value = mock_response

    client = GitLabClient("http://test", "token")
    # Mock safe_api_call to just run the function to avoid complicated mocking of retry logic here
    with patch("gitlab_utils.client.safe_api_call", side_effect=lambda f, *a, **k: f()):
        res = client._request("GET", "/test")
    assert res is None

@patch("gitlab_utils.client.GitLabClient._get")
def test_gitlab_client_get_paginated(mock_get):
    client = GitLabClient("http://test", "token")

    # 2 pages of data
    mock_get.side_effect = [
        [{"id": 1}, {"id": 2}],
        [{"id": 3}],
        []
    ]

    # per_page = 2
    res = client._get_paginated("/test", per_page=2, max_pages=5)
    assert len(res) == 3
    assert res[0]["id"] == 1
    assert res[2]["id"] == 3
    assert mock_get.call_count == 2 # Stopped because page 2 had < 2 items

@patch("time.sleep")
def test_safe_api_call_500_retry_and_fallback(mock_sleep):
    """Retries on 500 and eventually returns []."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    err_500 = requests.exceptions.HTTPError(response=mock_response)

    # Always fail
    mock_func = MagicMock(side_effect=err_500)
    assert safe_api_call(mock_func) == []
    assert mock_sleep.call_count == 4 # max_retries - 1

@patch("gitlab_utils.client._SESSION")
def test_gitlab_client_request_json(mock_session):
    """Normal response should return JSON."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"key": "val"}
    mock_session.request.return_value = mock_response

    client = GitLabClient("http://test", "token")
    with patch("gitlab_utils.client.safe_api_call", side_effect=lambda f, *a, **k: f()):
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
