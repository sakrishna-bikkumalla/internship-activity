import asyncio
import threading

import glabflow
import msgspec

_JSON_DECODER = msgspec.json.Decoder()


def _decode(raw) -> dict | list:
    """Decode raw bytes or pass through already-parsed data from glabflow."""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            return _JSON_DECODER.decode(raw)
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
                ssl=False,
                concurrency=25,
                timeout=30.0,
            )
            await gl.__aenter__()
            return gl

        try:
            fut = asyncio.run_coroutine_threadsafe(_enter(), self._loop)
            self._gl = fut.result(timeout=30)
        except Exception as e:
            self._gl = None

    def _request(self, method, endpoint, params=None):
        return self._run_sync(self._async_request(method, endpoint, params))

    async def _async_request(self, method, endpoint, params=None):
        gl = self._gl
        if not gl or not gl._session:
            return []

        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if path.startswith("/api/v4"):
            path = path[len("/api/v4"):]

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
        if not gl or not gl._session:
            return []

        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if path.startswith("/api/v4"):
            path = path[len("/api/v4"):]

        all_items: list = []
        p_params = {**(params or {}), "per_page": per_page}
        page_count = 0

        try:
            async for raw_page in gl.paginate(path, **p_params):
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
                asyncio.run_coroutine_threadsafe(
                    self._gl.__aexit__(None, None, None), self._loop
                )
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
        Reliable commit fetching for GitLab:
        1) List user projects
        2) Fetch commits per-project using /projects/{id}/repository/commits
        3) Filter locally by author identity to avoid global endpoint limitations
        """
        user_id = user_info.get("id") if isinstance(user_info, dict) else user_info
        if not user_id:
            print("[commits] user id missing; cannot fetch commits")
            return []

        projects = self.get_user_projects(user_id)
        if not projects:
            print(f"[commits] no projects found for user_id={user_id}")
            return []

        author_name = (user_info.get("name") or "").strip().lower() if isinstance(user_info, dict) else ""
        username = (user_info.get("username") or "").strip().lower() if isinstance(user_info, dict) else ""
        author_email = (
            (user_info.get("email") or user_info.get("public_email") or "").strip().lower()
            if isinstance(user_info, dict)
            else ""
        )

        name_candidates = {
            value
            for value in [
                author_name,
                username,
                username.replace("_", " ").replace(".", " ") if username else "",
                author_email.split("@")[0] if author_email else "",
            ]
            if value
        }
        email_candidates = {author_email} if author_email else set()

        author_queries = []
        for value in [author_email, author_name, username]:
            if value and value not in author_queries:
                author_queries.append(value)

        def _name_match(value):
            value = (value or "").strip().lower()
            if not value:
                return False
            normalized = value.replace("_", " ").replace(".", " ")
            for candidate in name_candidates:
                candidate_normalized = candidate.replace("_", " ").replace(".", " ")
                if (
                    value == candidate
                    or normalized == candidate_normalized
                    or candidate in value
                    or candidate_normalized in normalized
                ):
                    return True
            return False

        def _email_match(value):
            value = (value or "").strip().lower()
            if not value:
                return False
            local_part = value.split("@")[0]
            return value in email_candidates or local_part in name_candidates

        all_commits = []
        seen_commit_ids = set()
        scanned_projects = 0

        for project in projects:
            project_id = project.get("id")
            project_name = project.get("name") or project.get("path_with_namespace") or str(project_id)
            namespace_path = (project.get("namespace", {}) or {}).get("full_path", "").strip().lower()
            creator_id = project.get("creator_id")
            is_personal_project = namespace_path == username or creator_id == user_id
            project_scope = "Personal" if is_personal_project else "Contributed"
            if not project_id:
                continue

            scanned_projects += 1
            try:
                commit_batches = []

                if author_queries:
                    for author_query in author_queries:
                        commit_batches.append(
                            self.client._get_paginated(
                                f"/projects/{project_id}/repository/commits",
                                params={"all": True, "author": author_query},
                                per_page=100,
                                max_pages=50,
                            )
                        )

                if not any(commit_batches):
                    commit_batches.append(
                        self.client._get_paginated(
                            f"/projects/{project_id}/repository/commits",
                            params={"all": True},
                            per_page=100,
                            max_pages=50,
                        )
                    )

                for commits in commit_batches:
                    for commit in commits:
                        commit_id = commit.get("id") or commit.get("short_id")

                        commit_author_name = (commit.get("author_name") or "").strip().lower()
                        commit_author_email = (commit.get("author_email") or "").strip().lower()
                        commit_committer_name = (commit.get("committer_name") or "").strip().lower()
                        commit_committer_email = (commit.get("committer_email") or "").strip().lower()

                        if author_queries:
                            author_match = (
                                _name_match(commit_author_name)
                                or _name_match(commit_committer_name)
                                or _email_match(commit_author_email)
                                or _email_match(commit_committer_email)
                            )
                            if not author_match:
                                continue

                        if commit_id and commit_id in seen_commit_ids:
                            continue

                        if commit_id:
                            seen_commit_ids.add(commit_id)

                        commit["project_name"] = project_name
                        commit["project_id"] = project_id
                        commit["project_scope"] = project_scope
                        all_commits.append(commit)

            except Exception as e:
                print(f"[commits] failed for project_id={project_id} ({project_name}): {e}")

        print(
            f"[commits] scanned_projects={scanned_projects}, matched_commits={len(all_commits)} for user_id={user_id}"
        )
        return all_commits
