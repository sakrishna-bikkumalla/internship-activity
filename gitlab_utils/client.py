"""
Minimal wrapper used by the Streamlit app for user-level GitLab APIs.

This provides the small surface `app.py` expects (client.users.*) and
returns simple dicts/ints or "Error: ..." strings on failure so the app
can display friendly messages.
"""

import importlib
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional


class GitLabClient:
    def __init__(self, base_url: str, private_token: str, timeout: int = 10):
        gitlab = importlib.import_module("gitlab")
        self.gl = gitlab.Gitlab(base_url, private_token=private_token, timeout=timeout)
        try:
            self.gl.auth()
        except Exception:
            pass

        self.users = _Users(self.gl)


class _Users:
    def __init__(self, gl: Any):
        self.gl = gl

    # ---------------- User Profile ----------------

    def _to_basic_user(self, user_obj: Any) -> Dict[str, Any]:
        return {
            "id": getattr(user_obj, "id", None),
            "username": getattr(user_obj, "username", None),
            "name": getattr(user_obj, "name", None),
            "avatar_url": getattr(user_obj, "avatar_url", None),
            "web_url": getattr(user_obj, "web_url", None),
        }

    def get_by_userid(self, user_id: int) -> Optional[Dict[str, Any]]:
        user = self.gl.users.get(user_id)
        return self._to_basic_user(user)

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        users = self.gl.users.list(username=username)
        if users:
            return self._to_basic_user(users[0])

        users = self.gl.users.list(search=username)
        for u in users:
            if getattr(u, "username", "").lower() == username.lower():
                return self._to_basic_user(u)

        raise LookupError("User not found")

    # ---------------- Pagination Counter ----------------

    def _count_paginated(self, list_callable, *args, **kwargs) -> int:
        count, page, per_page = 0, 1, 100
        while True:
            items = list_callable(*args, page=page, per_page=per_page, **kwargs)
            if not items:
                break
            count += len(items)
            if len(items) < per_page:
                break
            page += 1
        return count

    # ---------------- Basic Counts ----------------

    def get_user_project_count(self, user_id: int):
        try:
            user = self.gl.users.get(user_id)
            return self._count_paginated(user.projects.list)
        except Exception as e:
            return f"Error: {e}"

    def get_user_group_count(self, user_id: int):
        try:
            return self._count_paginated(self.gl.groups.list, user_id=user_id)
        except Exception as e:
            return f"Error: {e}"

    # ---------------- Merge Request Counts ----------------

    def get_user_opened_mr_count(self, user_id: int):
        return self._count_paginated(self.gl.mergerequests.list, author_id=user_id, state="opened")

    def get_user_closed_mr_count(self, user_id: int):
        return self._count_paginated(self.gl.mergerequests.list, author_id=user_id, state="closed")

    def get_user_merged_mr_count(self, user_id: int):
        return self._count_paginated(self.gl.mergerequests.list, author_id=user_id, state="merged")

    def get_user_total_mr_count(self, user_id: int):
        return (
            self.get_user_opened_mr_count(user_id)
            + self.get_user_closed_mr_count(user_id)
            + self.get_user_merged_mr_count(user_id)
        )

    # ---------------- Project-wise MR Details ----------------

    def get_user_mr_details(self, user_id: int):
        mrs, page, per_page = [], 1, 50

        while True:
            items = self.gl.mergerequests.list(
                author_id=user_id, scope="all", page=page, per_page=per_page
            )
            if not items:
                break

            for mr in items:
                try:
                    project = self.gl.projects.get(mr.project_id)
                    project_name = project.name
                except Exception:
                    project_name = str(mr.project_id)

                mrs.append(
                    {
                        "Project": project_name,
                        "MR Title": mr.title,
                        "State": mr.state.capitalize(),
                        "URL": mr.web_url,
                    }
                )

            if len(items) < per_page:
                break
            page += 1

        return mrs

    # ---------------- Today Time Window ----------------

    def _today_time_window(self):
        now = datetime.now(timezone.utc)
        today = now.date()
        start = datetime.combine(today, time(0, 0), tzinfo=timezone.utc)
        end = datetime.combine(today, time(23, 59, 59), tzinfo=timezone.utc)
        return start, end

    # ---------------- Today's MR Summary ----------------

    def get_today_opened_mr_count(self, user_id: int):
        return self._get_today_mr_state_count(user_id, "opened")

    def get_today_closed_mr_count(self, user_id: int):
        return self._get_today_mr_state_count(user_id, "closed")

    def get_today_merged_mr_count(self, user_id: int):
        return self._get_today_mr_state_count(user_id, "merged")

    def _get_today_mr_state_count(self, user_id: int, state: str):
        start, end = self._today_time_window()
        count, page = 0, 1

        while True:
            items = self.gl.mergerequests.list(
                author_id=user_id, state=state, page=page, per_page=50
            )
            if not items:
                break

            for mr in items:
                if mr.created_at:
                    created = datetime.fromisoformat(mr.created_at.replace("Z", "+00:00"))
                    if start <= created <= end:
                        count += 1

            if len(items) < 50:
                break
            page += 1

        return count

    def get_today_total_mr_count(self, user_id: int):
        return (
            self.get_today_opened_mr_count(user_id)
            + self.get_today_closed_mr_count(user_id)
            + self.get_today_merged_mr_count(user_id)
        )
