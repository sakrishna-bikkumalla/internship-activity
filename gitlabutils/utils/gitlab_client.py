"""Lightweight GitLab client used by the Streamlit app.

This implementation uses direct HTTP requests to the GitLab REST API to
provide only the small subset of APIs required by the app (user lookup and
simple counts). It avoids depending on the external `gitlab_utils` SDK so
the local import works reliably in the bundled workspace.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests


class GitLabClient:
    def __init__(self, base_url: str, private_token: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": private_token})
        self.timeout = timeout
        self.users = _Users(self)


class _Users:
    def __init__(self, client: GitLabClient):
        self._client = client

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self._client.api_base}{path}"
        return self._client.session.get(url, params=params, timeout=self._client.timeout)

    def get_by_userid(self, userid: int) -> Optional[Dict[str, Any]]:
        try:
            r = self._get(f"/users/{userid}")
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._get("/users", params={"username": username})
            r.raise_for_status()
            items = r.json()
            return items[0] if items else None
        except Exception:
            return None

    def _count_from_endpoint(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        try:
            p = dict(params or {})
            p.update({"per_page": 1})
            r = self._get(path, params=p)
            r.raise_for_status()
            total = r.headers.get("X-Total")
            if total is not None:
                return int(total)
            # Fallback: return length of returned list
            data = r.json()
            return len(data) if isinstance(data, list) else 0
        except Exception as e:
            return f"Error: {e}"

    def get_user_project_count(self, user_id: int) -> Any:
        return self._count_from_endpoint(f"/users/{user_id}/projects")

    def get_user_group_count(self, user_id: int) -> Any:
        return self._count_from_endpoint(f"/users/{user_id}/groups")

    def get_user_issue_count(self, user_id: int) -> Any:
        return self._count_from_endpoint(
            "/issues", params={"author_id": user_id, "state": "opened"}
        )

    def get_user_mr_count(self, user_id: int) -> Any:
        return self._count_from_endpoint(
            "/merge_requests", params={"author_id": user_id, "state": "opened"}
        )


__all__ = ["GitLabClient"]
