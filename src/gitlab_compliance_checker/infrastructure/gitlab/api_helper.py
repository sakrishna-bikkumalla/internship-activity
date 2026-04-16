import asyncio
from typing import Any, Dict, List, Union, cast
from urllib.parse import urlparse

import glabflow
import msgspec

_JSON_DECODER = msgspec.json.Decoder()


def extract_path_from_url(input_str: Any) -> str:
    try:
        path = urlparse(str(input_str)).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return str(input_str).strip()


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


def get_project_branches(client, project_id: Union[int, str]) -> List[str]:
    """
    Fetch all branch names for a project.
    `client` is the GitLabClient wrapper (infrastructure/gitlab/client.py).
    """
    try:
        branches = client._get_paginated(
            f"/projects/{str(project_id).replace('/', '%2F')}/repository/branches",
            per_page=100,
            max_pages=10,
        )
        return sorted(b.get("name", "") for b in (branches or []) if b.get("name"))
    except Exception:
        return []


def get_user_from_token(base_url: str, token: str) -> Union[Dict[str, Any], str]:
    async def _fetch():
        api_base = base_url.rstrip("/") + "/api/v4"
        async with glabflow.Client(
            base_url=api_base,
            token=token,
            timeout=15,
            ssl=False,
        ) as gl:
            raw = await gl.get("/user")
            user = _decode(raw)
            if user and isinstance(user, dict):
                return user
            return "Error validating token: User is None"

    try:
        # Cast the result of asyncio.run to satisfy Mypy
        return cast(Union[Dict[str, Any], str], asyncio.run(_fetch()))
    except Exception as e:
        return f"Error validating token: {e}"


def get_user_groups_by_token(base_url: str, token: str) -> List[Dict[str, Any]]:
    async def _fetch():
        api_base = base_url.rstrip("/") + "/api/v4"
        result = []
        async with glabflow.Client(
            base_url=api_base,
            token=token,
            timeout=15,
            ssl=False,
        ) as gl:
            async for raw_page in gl.paginate("/groups", membership="true", per_page=100):
                page = _decode(raw_page)
                if isinstance(page, list):
                    result.extend(page)
        return result

    try:
        return cast(List[Dict[str, Any]], asyncio.run(_fetch()))
    except Exception:
        return []
