import asyncio

import glabflow
import msgspec

DEFAULT_TIMEOUT = 15

_JSON_DECODER = msgspec.json.Decoder()


def _decode(raw) -> dict | list:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return _JSON_DECODER.decode(raw)
        except Exception:
            return {}
    return {}


def get_user_from_token(base_url: str, token: str):
    """
    Fetch authenticated user using PRIVATE-TOKEN.
    """
    async def _fetch():
        api_base = base_url.rstrip("/") + "/api/v4"
        async with glabflow.Client(
            base_url=api_base,
            token=token,
            timeout=DEFAULT_TIMEOUT,
            ssl=False,
        ) as gl:
            raw = await gl.get("/user")
            user = _decode(raw)
            if user and isinstance(user, dict):
                return user
            raise Exception("Authentication failed or user not found.")

    return asyncio.run(_fetch())


def get_user_groups(base_url: str, token: str):
    """
    Fetch groups where authenticated user has membership.
    """
    async def _fetch():
        api_base = base_url.rstrip("/") + "/api/v4"
        result = []
        async with glabflow.Client(
            base_url=api_base,
            token=token,
            timeout=DEFAULT_TIMEOUT,
            ssl=False,
        ) as gl:
            async for raw_page in gl.paginate("/groups", membership="true", per_page=100):
                page = _decode(raw_page)
                if isinstance(page, list):
                    result.extend(page)
        return result

    return asyncio.run(_fetch())


def validate_token(base_url: str, token: str) -> bool:
    """
    Returns True if token is valid.
    """
    try:
        get_user_from_token(base_url, token)
        return True
    except Exception:
        return False
