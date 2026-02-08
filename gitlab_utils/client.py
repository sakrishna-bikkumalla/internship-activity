"""Minimal wrapper used by the Streamlit app for user-level GitLab APIs.

This provides the small surface `app.py` expects (client.users.*) and
returns simple dicts/ints or "Error: ..." strings on failure so the app
can display friendly messages.
"""

import importlib
from typing import Any, Dict, Optional


class GitLabClient:
    def __init__(self, base_url: str, private_token: str, timeout: int = 10):
        gitlab = importlib.import_module("gitlab")
        self.gl = gitlab.Gitlab(base_url, private_token=private_token, timeout=timeout)
        try:
            self.gl.auth()
        except Exception:
            # auth may not be required until calls are made; ignore here
            pass

        self.users = _Users(self.gl)


class _Users:
    def __init__(self, gl: Any):
        self.gl = gl

    def _to_basic_user(self, user_obj: Any) -> Dict[str, Any]:
        return {
            "id": getattr(user_obj, "id", None),
            "username": getattr(user_obj, "username", None),
            "name": getattr(user_obj, "name", None),
            "avatar_url": getattr(user_obj, "avatar_url", None),
            "web_url": getattr(user_obj, "web_url", None),
        }

    def get_by_userid(self, user_id: int) -> Optional[Dict[str, Any]]:
        try:
            user = self.gl.users.get(user_id)
            return self._to_basic_user(user)
        except Exception:
            raise

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            users = self.gl.users.list(username=username)
            if users:
                return self._to_basic_user(users[0])

            # fallback: try search
            users = self.gl.users.list(search=username)
            for u in users:
                if getattr(u, "username", "").lower() == username.lower():
                    return self._to_basic_user(u)

            raise LookupError("User not found")

        except Exception:
            raise

    def _count_paginated(self, list_callable, *args, **kwargs) -> int:
        count = 0
        page = 1
        per_page = 100

        while True:
            try:
                items = list_callable(*args, page=page, per_page=per_page, **kwargs)
            except TypeError:
                items = list_callable(*args, **kwargs)

            if not items:
                break

            count += len(items)

            if len(items) < per_page:
                break

            page += 1

        return count

    def get_user_project_count(self, user_id: int) -> Any:
        try:
            user = self.gl.users.get(user_id)
            return self._count_paginated(user.projects.list)
        except Exception as e:
            return f"Error: {e}"

    def get_user_group_count(self, user_id: int) -> Any:
        try:
            return self._count_paginated(self.gl.groups.list, user_id=user_id)
        except Exception as e:
            return f"Error: {e}"

    def get_user_issue_count(self, user_id: int) -> Any:
        try:
            return self._count_paginated(self.gl.issues.list, author_id=user_id, state="opened")
        except Exception as e:
            return f"Error: {e}"

    # ✅ Open Merge Requests
    def get_user_mr_count(self, user_id: int) -> Any:
        try:
            return self._count_paginated(
                self.gl.mergerequests.list,
                author_id=user_id,
                state="opened",
            )
        except Exception as e:
            return f"Error: {e}"

    # ✅ Closed Merge Requests
    def get_user_closed_mr_count(self, user_id: int) -> Any:
        try:
            return self._count_paginated(
                self.gl.mergerequests.list,
                author_id=user_id,
                state="closed",
            )
        except Exception as e:
            return f"Error: {e}"

    # ✅ Total Merge Requests
    def get_user_total_mr_count(self, user_id: int) -> Any:
        try:
            open_count = self.get_user_mr_count(user_id)
            closed_count = self.get_user_closed_mr_count(user_id)

            if isinstance(open_count, int) and isinstance(closed_count, int):
                return open_count + closed_count

            return "Error: Could not calculate total MRs"

        except Exception as e:
            return f"Error: {e}"
