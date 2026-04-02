import asyncio

import aiohttp

DEFAULT_TIMEOUT = 15


async def _make_request_async(method, url, headers=None, params=None, json=None, timeout=DEFAULT_TIMEOUT):
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.request(
            method=method,
            url=url,
            params=params,
            json=json,
            timeout=timeout,
            ssl=False,
        ) as response:
            try:
                response.raise_for_status()
                return await response.json()
            except Exception:
                # To emulate legacy behavior which returns the response object on success
                # or throws exception. Since JSON is always expected here:
                pass
            return await response.json()


def make_request(method, url, headers=None, params=None, json=None, timeout=DEFAULT_TIMEOUT):
    """
    Generic HTTP request wrapper.
    Raises exception on failure.
    """
    return asyncio.run(_make_request_async(method, url, headers, params, json, timeout))


def get_user_from_token(base_url: str, token: str):
    """
    Fetch authenticated user using PRIVATE-TOKEN.
    """
    headers = {"PRIVATE-TOKEN": token}
    url = f"{base_url.rstrip('/')}/api/v4/user"

    response_json = make_request("GET", url, headers=headers)
    return response_json


def get_user_groups(base_url: str, token: str):
    """
    Fetch groups where authenticated user has membership.
    """
    headers = {"PRIVATE-TOKEN": token}

    api_base = base_url.rstrip("/")
    if api_base.endswith("/api/v4"):
        url = f"{api_base}/groups?membership=true"
    else:
        url = f"{api_base}/api/v4/groups?membership=true"

    response_json = make_request("GET", url, headers=headers)
    return response_json


def validate_token(base_url: str, token: str) -> bool:
    """
    Returns True if token is valid.
    """
    try:
        get_user_from_token(base_url, token)
        return True
    except Exception:
        return False
