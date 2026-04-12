import asyncio
from urllib.parse import urlparse

import glabflow
import msgspec

_JSON_DECODER = msgspec.json.Decoder()


def extract_path_from_url(input_str):
    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return str(input_str).strip()


def _decode(raw) -> dict | list:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return _JSON_DECODER.decode(raw)
        except Exception:
            return {}
    return {}


def get_project_branches(client, project_id: int) -> list[str]:
    """
    Fetch all branch names for a project.
    `client` is the GitLabClient wrapper (infrastructure/gitlab/client.py).
    """
    try:
        branches = client._get_paginated(
            f"/projects/{project_id}/repository/branches",
            per_page=100,
            max_pages=10,
        )
        return sorted(b.get("name", "") for b in (branches or []) if b.get("name"))
    except Exception:
        return []


def get_user_from_token(base_url, token):
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
        return asyncio.run(_fetch())
    except Exception as e:
        return f"Error validating token: {e}"


def get_user_groups_by_token(base_url, token):
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
        return asyncio.run(_fetch())
    except Exception as e:
        return f"Error fetching groups: {e}"
