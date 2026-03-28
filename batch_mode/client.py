import asyncio

import aiohttp
import nest_asyncio

nest_asyncio.apply()


class GitLabClient:
    def __init__(self, base_url, private_token):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.headers = {"PRIVATE-TOKEN": private_token}
        self.users = GitLabUsersAPI(self)
        self._loop = self._get_or_create_loop()

    def _get_or_create_loop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    async def _async_request(self, method, endpoint, params=None):
        url = f"{self.api_base}{endpoint}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.request(method, url, params=params, timeout=30, ssl=False) as response:
                response.raise_for_status()
                if response.status == 204:
                    return None
                return await response.json()

    def _request(self, method, endpoint, params=None):
        return self._loop.run_until_complete(self._async_request(method, endpoint, params))

    def _get(self, endpoint, params=None):
        return self._request("GET", endpoint, params=params)


    def _get_paginated(self, endpoint, params=None, per_page=100, max_pages=20):
        all_items = []
        base_params = dict(params or {})

        for page in range(1, max_pages + 1):
            page_params = {**base_params, "per_page": per_page, "page": page}
            batch = self._get(endpoint, params=page_params)
            if not isinstance(batch, list) or not batch:
                break
            all_items.extend(batch)
            if len(batch) < per_page:
                break

        return all_items


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
            # Some GitLab instances may not expose this endpoint for all tokens.
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

                # Fallback: if author-filtered fetch returns nothing, query all commits and
                # filter locally by author identity.
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
