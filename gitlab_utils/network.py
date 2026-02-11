
import requests


DEFAULT_TIMEOUT = 15


def make_request(method, url, headers=None, params=None, json=None, timeout=DEFAULT_TIMEOUT):
    """
    Generic HTTP request wrapper.
    Raises exception on failure.
    """
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        json=json,
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def get_user_from_token(base_url: str, token: str):
    """
    Fetch authenticated user using PRIVATE-TOKEN.
    """
    headers = {"PRIVATE-TOKEN": token}
    url = f"{base_url.rstrip('/')}/api/v4/user"

    response = make_request("GET", url, headers=headers)
    return response.json()


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

    response = make_request("GET", url, headers=headers)
    return response.json()


def validate_token(base_url: str, token: str) -> bool:
    """
    Returns True if token is valid.
    """
    try:
        get_user_from_token(base_url, token)
        return True
    except Exception:
        return False
