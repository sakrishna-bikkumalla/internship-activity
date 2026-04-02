import gitlab

DEFAULT_TIMEOUT = 15


def get_user_from_token(base_url: str, token: str):
    """
    Fetch authenticated user using PRIVATE-TOKEN.
    """
    try:
        gl = gitlab.Gitlab(url=base_url, private_token=token, timeout=DEFAULT_TIMEOUT, ssl_verify=False)
        gl.auth()
        if gl.user:
            return gl.user.as_dict()
        raise Exception("Authentication failed or user not found.")
    except Exception:
        raise


def get_user_groups(base_url: str, token: str):
    """
    Fetch groups where authenticated user has membership.
    """
    try:
        gl = gitlab.Gitlab(url=base_url, private_token=token, timeout=DEFAULT_TIMEOUT, ssl_verify=False)
        groups = gl.groups.list(membership=True, all=True)
        return [g.as_dict() for g in groups]
    except Exception:
        raise


def validate_token(base_url: str, token: str) -> bool:
    """
    Returns True if token is valid.
    """
    try:
        gl = gitlab.Gitlab(url=base_url, private_token=token, timeout=DEFAULT_TIMEOUT, ssl_verify=False)
        gl.auth()
        return True
    except Exception:
        return False
