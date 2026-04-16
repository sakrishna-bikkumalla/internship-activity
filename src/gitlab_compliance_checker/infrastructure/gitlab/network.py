import asyncio
import os
import threading
from typing import Any, Dict, List, Union

import glabflow
import msgspec

_GLOBAL_LOOP = asyncio.new_event_loop()
_GLOBAL_LOOP_THREAD = threading.Thread(target=_GLOBAL_LOOP.run_forever, daemon=True)
_GLOBAL_LOOP_THREAD.start()


def _run_sync(coro):
    return asyncio.run_coroutine_threadsafe(coro, _GLOBAL_LOOP).result()


DEFAULT_TIMEOUT = 15

_JSON_DECODER = msgspec.json.Decoder()


def _decode(raw: Any) -> Union[Dict[Any, Any], List[Any]]:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            val = _JSON_DECODER.decode(raw)
            if isinstance(val, (dict, list)):
                return val
            return {}
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
            ssl=os.environ.get("GITLAB_SSL_VERIFY", "True").lower() in ("true", "1", "t"),
        ) as gl:
            raw = await gl.get("/user")
            user = _decode(raw)
            if user and isinstance(user, dict):
                return user
            raise Exception("Authentication failed or user not found.")

    return _run_sync(_fetch())


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
            ssl=os.environ.get("GITLAB_SSL_VERIFY", "True").lower() in ("true", "1", "t"),
        ) as gl:
            async for raw_page in gl.paginate("/groups", membership="true", per_page=100):
                page = _decode(raw_page)
                if isinstance(page, list):
                    result.extend(page)
        return result

    return _run_sync(_fetch())


def validate_token(base_url: str, token: str) -> bool:
    """
    Returns True if token is valid.
    """
    try:
        get_user_from_token(base_url, token)
        return True
    except Exception:
        return False
