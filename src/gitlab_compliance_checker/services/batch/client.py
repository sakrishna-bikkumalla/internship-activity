import asyncio
import os
import threading
from typing import Any, Dict, List, Union

import glabflow
import msgspec

_JSON_DECODER = msgspec.json.Decoder()


def _decode(raw: Any) -> Union[Dict[Any, Any], List[Any]]:
    """Decode raw bytes or pass through already-parsed data from glabflow."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            val = _JSON_DECODER.decode(raw)
            if isinstance(val, (dict, list)):
                return val
            return []
        except Exception:
            return []
    return []


class GitLabClient:
    def __init__(self, base_url, private_token):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.private_token = private_token
        self._gl: glabflow.Client | None = None

        # Background event loop — same pattern as infrastructure/gitlab/client.py
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        self._init_gl_client()
        self.users = GitLabUsersAPI(self)

    def _run_sync(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def _init_gl_client(self):
        async def _enter():
            gl = glabflow.Client(
                base_url=self.api_base,
                token=self.private_token,
                ssl=os.environ.get("GITLAB_SSL_VERIFY", "True").lower() in ("true", "1", "t"),
                concurrency=25,
                timeout=30.0,
            )
            # CRITICAL: Prevent event loop contention in Streamlit threads
            await gl.__aenter__()
            return gl

        try:
            fut = asyncio.run_coroutine_threadsafe(_enter(), self._loop)
            self._gl = fut.result(timeout=30)
        except Exception:
            self._gl = None

    def _request(self, method, endpoint, params=None):
        return self._run_sync(self._async_request(method, endpoint, params))

    async def _async_request(self, method, endpoint, params=None):
        gl = self._gl
        if not gl:
            return []

        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if path.startswith("/api/v4"):
            path = path[len("/api/v4") :]

        try:
            if method.upper() == "GET":
                raw = await gl.get(path, **(params or {}))
            elif method.upper() == "POST":
                raw = await gl.post(path, json=params or {})
            else:
                raw = await gl.get(path, **(params or {}))
            return _decode(raw)
        except glabflow.NotFoundError:
            return []
        except Exception:
            return []

    def _get(self, endpoint, params=None):
        return self._request("GET", endpoint, params=params)

    def _get_paginated(self, endpoint, params=None, per_page=100, max_pages=20):
        return self._run_sync(self._async_get_paginated(endpoint, params, per_page, max_pages))

    async def _async_get_paginated(self, endpoint, params=None, per_page=100, max_pages=20):
        gl = self._gl
        if not gl:
            return []

        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if path.startswith("/api/v4"):
            path = path[len("/api/v4") :]

        all_items: list = []
        p_params = {**(params or {}), "per_page": per_page}
        page_count = 0

        try:
            # Set ordered=False for maximum throughput during parallel fetching
            async for raw_page in gl.paginate(path, ordered=False, **p_params):
                page_count += 1
                page_data = _decode(raw_page)
                if isinstance(page_data, list):
                    all_items.extend(page_data)
                    if len(page_data) < per_page:
                        break
                elif isinstance(page_data, dict):
                    all_items.append(page_data)
                if page_count >= max_pages:
                    break
        except Exception:
            pass

        return all_items

    def __del__(self):
        try:
            if self._gl is not None:
                asyncio.run_coroutine_threadsafe(self._gl.__aexit__(None, None, None), self._loop)
            self._loop.stop()
        except Exception:
            pass


class GitLabUsersAPI:
    def __init__(self, client):
        self.client = client

    def _normalize_user(self, user):
        if not user:
            return None
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "name": user.get("name"),
            "web_url": user.get("web_url"),
            "avatar_url": user.get("avatar_url"),
            "public_email": user.get("public_email"),
            "email": user.get("email") or user.get("public_email"),
            "created_at": user.get("created_at"),
        }

    def get_by_username(self, username):
        users = self.client._get("/users", params={"username": username})
        if not users:
            raise ValueError(f"No GitLab user found for username '{username}'.")
        return self._normalize_user(users[0])

    def get_by_userid(self, user_id):
        user = self.client._get(f"/users/{user_id}")
        return self._normalize_user(user)

    def get_user_projects(self, user_id):
        """
        Return all relevant projects for the user, including:
        - owned projects
        - membership/contributed projects
        - contributed_projects endpoint (when available)
        """
        project_map = {}

        def _merge(projects):
            for project in projects or []:
                pid = project.get("id")
                if pid:
                    project_map[pid] = project

        _merge(
            self.client._get_paginated(
                f"/users/{user_id}/projects",
                params={"simple": True, "archived": False, "owned": True},
            )
        )

        _merge(
            self.client._get_paginated(
                f"/users/{user_id}/projects",
                params={"simple": True, "archived": False, "membership": True},
            )
        )

        try:
            _merge(
                self.client._get_paginated(
                    f"/users/{user_id}/contributed_projects",
                    params={"simple": True, "archived": False},
                )
            )
        except Exception:
            pass

        return list(project_map.values())

    def get_user_groups(self, user_id):
        return self.client._get_paginated(f"/users/{user_id}/groups")

    def get_user_project_count(self, user_id):
        try:
            return len(self.get_user_projects(user_id))
        except Exception as e:
            return f"Error: {e}"

    def get_user_group_count(self, user_id):
        try:
            groups = self.get_user_groups(user_id)
            return len(groups)
        except Exception as e:
            return f"Error: {e}"

    def get_user_issues(self, user_id):
        return self.client._get_paginated(
            "/issues",
            params={"author_id": user_id, "scope": "all", "order_by": "created_at"},
        )

    def get_user_issue_count(self, user_id):
        try:
            return len(self.get_user_issues(user_id))
        except Exception as e:
            return f"Error: {e}"

    def get_user_merge_requests(self, user_id):
        return self.client._get_paginated(
            "/merge_requests",
            params={"author_id": user_id, "scope": "all", "order_by": "created_at"},
        )

    def get_user_mr_count(self, user_id):
        try:
            return len(self.get_user_merge_requests(user_id))
        except Exception as e:
            return f"Error: {e}"

    def get_user_commits(self, user_info):
        """
        Ultra-fast commit fetching for GitLab:
        1) Parallel project scanning (asyncio.gather).
        2) Single-pass fetching per project (fetch once, match locally).
        3) Refined identity matching (Username -> Email fallback).
        """
        user_id = user_info.get("id") if isinstance(user_info, dict) else user_info
        if not user_id:
            return []

        projects = self.get_user_projects(user_id)
        if not projects:
            return []

        target_username = (user_info.get("username") or "").strip().lower() if isinstance(user_info, dict) else ""
        target_email = (
            (user_info.get("email") or user_info.get("public_email") or "").strip().lower()
            if isinstance(user_info, dict)
            else ""
        )

        all_commits = []
        seen_commit_ids = set()
        lock = threading.Lock()

        async def _fetch_project_commits(project):
            p_id = project.get("id")
            p_name = project.get("name") or project.get("path_with_namespace") or str(p_id)
            namespace_path = (project.get("namespace", {}) or {}).get("full_path", "").strip().lower()
            creator_id = project.get("creator_id")
            is_personal = namespace_path == target_username or creator_id == user_id
            scope = "Personal" if is_personal else "Contributed"

            try:
                # Use strict local matching instead of server-side 'author' filter
                # to ensure we don't miss commits due to API email/username inconsistencies.
                api_params = {"all": True}

                # Single-pass fetch for all commits in the project
                commits = await self.client._async_get_paginated(
                    f"/projects/{p_id}/repository/commits",
                    params=api_params,
                    per_page=100,
                    max_pages=50,
                )

                project_commits = []
                for commit in commits:
                    c_id = commit.get("id") or commit.get("short_id")
                    if not c_id:
                        continue

                    # Local Identity Matching: Strict Mode
                    author = commit.get("author") or {}
                    c_username = (author.get("username") or "").strip().lower()
                    c_auth_email = (commit.get("author_email") or "").strip().lower()
                    c_comm_email = (commit.get("committer_email") or "").strip().lower()
                    c_author_name = (commit.get("author_name") or "").strip().lower()
                    c_email_local = c_auth_email.split("@")[0] if "@" in c_auth_email else c_auth_email

                    is_match = False
                    # Priority 1: Exact GitLab Username match
                    if target_username and c_username == target_username:
                        is_match = True
                    # Priority 2: Exact Email match
                    elif target_email and (c_auth_email == target_email or c_comm_email == target_email):
                        is_match = True
                    # Priority 3: Exact Email local part match
                    elif target_username and c_email_local == target_username:
                        is_match = True
                    elif target_email and "@" in target_email:
                        if target_email.split("@")[0] == c_email_local:
                            is_match = True

                    # Priority 4: Exact Normalized Name match
                    if not is_match:
                        import re

                        def _ns(s):
                            return re.sub(r"[\s_\.\-]", "", (s or "").lower())

                        ns_cname = _ns(c_author_name)
                        ns_uname = _ns(target_username)
                        ns_aname = _ns((user_info.get("name") if isinstance(user_info, dict) else ""))

                        # Match if the commit name matches the GitLab display name or username exactly after normalization
                        if ns_cname and (ns_cname == ns_uname or ns_cname == ns_aname):
                            is_match = True
                        # Also allow matching if the normalized display name matches the commit name
                        elif ns_aname and ns_cname == ns_aname:
                            is_match = True

                    if not is_match:
                        continue

                    with lock:
                        if c_id in seen_commit_ids:
                            continue
                        seen_commit_ids.add(c_id)

                    commit["project_name"] = p_name
                    commit["project_id"] = p_id
                    commit["project_scope"] = scope
                    project_commits.append(commit)
                return project_commits
            except Exception as e:
                print(f"[commits] failed for project {p_name}: {e}")
                return []

        async def _process_all():
            # Process in batches of 10 to respect rate limits
            tasks = [_fetch_project_commits(p) for p in projects]
            results = []
            for i in range(0, len(tasks), 10):
                batch = tasks[i : i + 10]
                results.extend(await asyncio.gather(*batch))
            return [c for sub in results for c in sub]

        all_commits = self.client._run_sync(_process_all())

        print(
            f"[commits] scanned_projects={len(projects)}, matched_commits={len(all_commits)} for username={target_username}"
        )
        return all_commits
