import asyncio
import re
import threading
from datetime import datetime, timezone
from typing import Any

import aiohttp
import gitlab

# import nest_asyncio # Causes "Timeout context manager should be used inside a task" in aiohttp 3.11+


async def safe_api_call_async(func, *args, **kwargs):
    """
    Async safe wrapper for GitLab API calls with aggressive retry logic and 429 handling.
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_limit = int(retry_after)
                        if wait_limit > 60:
                            raise Exception(
                                f"GitLab API Rate Limit Exceeded. Please try again after {wait_limit} seconds."
                            )
                    except (ValueError, TypeError):
                        pass

                wait_time = 5 * (attempt + 1)
                print(f"Rate limited (429) on {e.request_info.url}. Waiting {wait_time}s...")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise Exception("GitLab API Rate Limit Exceeded (429 Too Many Requests). Max retries reached.")

            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return []
        except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError) as e:
            wait_time = 5 * (attempt + 1)
            print(f"Connection Error: {e}. Waiting {wait_time}s...")
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            return []
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            print(f"FAILED API CALL: {e}")
            return []
    return []


# BATCH_USERNAMES etc constant
BATCH_USERNAMES: list[str] = [
    "prav2702",
    "saikrishna_b",
    "MohanaSriBhavitha",
    "praneethashish",
    "kanukuntagreeshma2004",
    "vandana1735",
    "vandana_rajuldev",
    "Mukthanand21",
    "Shanmukh16",
    "Sathwikareddy_Damanagari",
    "Sahasraa",
    "laxmanreddypatlolla",
    "Abhilash653",
    "LagichettyKushal",
    "Lakshy",
    "Suma2304",
    "koushik_18",
    "kumari123",
    "Habeebunissa",
    "Bhaskar_Battula",
    "Pranav_rs",
    "vai5h",
    "Saiharshavardhan",
    "Rushika_1105",
    "swarna_4539",
    "satish05",
    "aravindswamy",
    "pavaninagireddi",
    "jeevana_31",
    "saiteja3005",
    "SandhyaRani_111",
    "klaxmi1908",
    "Kaveri_Mamidi",
    "Pavani_Pothuganti",
    "prashanth0812",
    "dasarajulavaishnavi04",
    "ashrithakunjeti",
    "srilathabandari",
    "vemurispriya",
]

_ZERO_ROW: dict[str, Any] = {
    "Username": "",
    "Closed MRs": 0,
    "No Desc": 0,
    "No Issues": 0,
    "No Time Spent": 0,
    "No Unit Tests": 0,
    "Failed Pipeline": 0,
    "No Semantic Commits": 0,
    "No Internal Review": 0,
    "Merge > 1 Week": 0,
    "Merge > 2 Days": 0,
}

_ZERO_ISSUE_ROW: dict[str, Any] = {
    "Username": "",
    "Total Assigned": 0,
    "Opened Issues": 0,
    "Closed Issues": 0,
    "No Desc": 0,
    "No Labels": 0,
    "No Milestone": 0,
    "No Time Spent": 0,
    "Long Open Time (>2 days)": 0,
    "No Semantic Title": 0,
}


class GitLabClient:
    def __init__(self, base_url, private_token):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.headers = {"PRIVATE-TOKEN": private_token}
        self.private_token = private_token
        self.error_msg = None
        self._client = None
        self._session = None

        # We run a separate background thread for the asyncio loop to avoid
        # conflicts with Streamlit's own execution model and nest_asyncio quirks.
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        # The semaphore must be created in the same loop it will be used in.
        # We use a Future to wait for it.
        self._sem = None
        self._init_sem()

    def _run_event_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _init_sem(self):
        async def create_sem():
            return asyncio.Semaphore(25)

        fut = asyncio.run_coroutine_threadsafe(create_sem(), self._loop)
        self._sem = fut.result()

    def _run_sync(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    async def _get_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector, headers=self.headers)
        return self._session

    @property
    def client(self):
        """Lazy-loaded python-gitlab client."""
        if self._client is None:
            # Note: We keep sidebar writes here for UI feedback
            try:
                self._client = gitlab.Gitlab(
                    url=self.base_url, private_token=self.private_token, timeout=10, ssl_verify=False
                )
            except Exception as e:
                self.error_msg = str(e)
                self._client = None
        return self._client

    async def _async_request(self, method, endpoint, params=None):
        url = endpoint if endpoint.startswith("http") else f"{self.api_base}{endpoint}"
        session = await self._get_session()

        # aiohttp requires params to be str/int/float, not bool
        if params:
            params = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()}

        async def make_request():
            async with self._sem:
                async with session.request(method, url, params=params, timeout=30) as response:
                    response.raise_for_status()
                    if response.status == 204:
                        return None
                    return await response.json()

        return await safe_api_call_async(make_request)

    async def _evaluate_single_mr(self, mr: dict) -> tuple[str, dict]:
        uname = mr.get("_username", "unknown")
        pid, iid = mr["project_id"], mr["iid"]
        flags = {
            "is_terminal": mr.get("state") in ("merged", "closed"),
            "is_merged": mr.get("state") == "merged",
            "is_closed_rejected": mr.get("state") == "closed",
            "no_desc": False,
            "no_issues": False,
            "no_time": False,
            "no_unit_tests": False,
            "failed_pipe": False,
            "no_semantic_commits": False,
            "no_internal_review": True,
            "merge_gt_2_days": False,
            "merge_gt_1_week": False,
        }

        try:
            desc = mr.get("description") or ""
            if not str(desc).strip():
                flags["no_desc"] = True

            # 1. Pipeline Check
            pipeline = mr.get("pipeline")
            if pipeline and isinstance(pipeline, dict):
                if pipeline.get("status") == "failed":
                    flags["failed_pipe"] = True
            elif flags["is_closed_rejected"]:
                pl = await self._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/pipelines")
                if pl and isinstance(pl, list) and len(pl) > 0:
                    if pl[0].get("status") == "failed":
                        flags["failed_pipe"] = True

            # 2. Time Spent Check
            ts = mr.get("time_stats", {})
            if isinstance(ts, dict) and ts.get("total_time_spent", 0) == 0:
                flags["no_time"] = True

            # 3. Semantic Commits Check
            m_commits = await self._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/commits")
            if m_commits and isinstance(m_commits, list):
                has_any_semantic = any(
                    re.match(
                        r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?:",
                        str(c.get("message", "")).lower(),
                    )
                    for c in m_commits
                )
                flags["no_semantic_commits"] = not has_any_semantic
            else:
                title_lower = str(mr.get("title") or "").lower()
                if not re.match(
                    r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?:", title_lower
                ):
                    flags["no_semantic_commits"] = True

            # 4. Internal Review
            m_notes = await self._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/notes")
            mr_author_id = mr.get("author", {}).get("id")
            has_human_review = any(
                not n.get("system") and n.get("author", {}).get("id") != mr_author_id for n in (m_notes or [])
            )
            if not has_human_review and mr.get("upvotes", 0) > 0:
                has_human_review = True
            flags["no_internal_review"] = not has_human_review

            # 5. Issues check
            content = f"{mr.get('title', '')} {mr.get('description', '')}"
            if re.search(r"#\d+|issue\s*#?\d+|\[\d+\]", content, re.IGNORECASE):
                flags["no_issues"] = False
            else:
                iss = await self._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/issues")
                if not iss:
                    flags["no_issues"] = True

            # 6. Unit Tests check
            title_l = str(mr.get("title") or "").lower()
            if "test" in title_l or "spec" in title_l:
                flags["no_unit_tests"] = False
            else:
                chg = await self._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/changes")
                h_tests = any(
                    "test" in str(c.get("new_path", "")).lower() or "spec" in str(c.get("new_path", "")).lower()
                    for c in (chg.get("changes", []) if isinstance(chg, dict) else [])
                )
                flags["no_unit_tests"] = not h_tests

            # Time tracking
            created_s = mr.get("created_at")
            merged_s = mr.get("merged_at")
            if created_s:
                created_dt = datetime.strptime(created_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                end_dt = (
                    datetime.strptime(merged_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    if merged_s
                    else (
                        datetime.strptime(mr.get("closed_at", "")[:19], "%Y-%m-%dT%H:%M:%S").replace(
                            tzinfo=timezone.utc
                        )
                        if mr.get("state") == "closed" and mr.get("closed_at")
                        else datetime.now(timezone.utc)
                    )
                )
                diff = (end_dt - created_dt).total_seconds() / 86400
                if diff > 2:
                    flags["merge_gt_2_days"] = True
                if diff > 7:
                    flags["merge_gt_1_week"] = True
        except Exception:
            pass
        return uname, flags

    async def _fetch_user_mrs(
        self,
        uname: str,
        project_id=None,
        group_id=None,
        mr_scope: str = "author",
    ) -> list[dict]:
        u_data = await self._async_request("GET", "/users", params={"username": uname})
        target_user = next(
            (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(uname).lower()), None
        )
        if not target_user:
            return []
        scope = str(mr_scope or "author").strip().lower()
        if scope not in {"author", "assignee"}:
            scope = "author"

        user_filter_key = "assignee_id" if scope == "assignee" else "author_id"
        params = {user_filter_key: str(target_user["id"]), "scope": "all", "per_page": "100"}
        if project_id:
            params["project_id"] = project_id
        if group_id:
            params["group_id"] = group_id
        mrs = await self._async_request("GET", "/merge_requests", params=params)
        for mr in mrs or []:
            mr["_username"] = uname
        return mrs or []

    async def _batch_evaluate_mrs_async(
        self,
        usernames: list[str],
        project_id=None,
        group_id=None,
        mr_scope: str = "author",
    ) -> list[dict]:
        result_map = {u: {**_ZERO_ROW, "Username": u} for u in usernames}
        user_tasks = [self._fetch_user_mrs(u, project_id, group_id, mr_scope) for u in usernames]
        all_users_mrs = await asyncio.gather(*user_tasks)
        all_mrs = [mr for sublist in all_users_mrs for mr in sublist]
        eval_results = await asyncio.gather(*[self._evaluate_single_mr(mr) for mr in all_mrs])
        for uname, f in eval_results:
            if uname in result_map and f.get("is_closed_rejected"):
                row = result_map[uname]
                row["Closed MRs"] += 1
                if f.get("failed_pipe"):
                    row["Failed Pipeline"] += 1
                if f.get("no_desc"):
                    row["No Desc"] += 1
                if f.get("no_issues"):
                    row["No Issues"] += 1
                if f.get("no_time"):
                    row["No Time Spent"] += 1
                if f.get("no_unit_tests"):
                    row["No Unit Tests"] += 1
                if f.get("no_semantic_commits"):
                    row["No Semantic Commits"] += 1
                if f.get("no_internal_review"):
                    row["No Internal Review"] += 1
                if f.get("merge_gt_1_week"):
                    row["Merge > 1 Week"] += 1
                if f.get("merge_gt_2_days"):
                    row["Merge > 2 Days"] += 1
        return sorted(result_map.values(), key=lambda r: r["Username"])

    def batch_evaluate_mrs(self, usernames, project_id=None, group_id=None, mr_scope: str = "author"):
        return self._run_sync(self._batch_evaluate_mrs_async(usernames, project_id, group_id, mr_scope))

    async def _evaluate_single_issue(self, issue: dict) -> tuple[str, dict]:
        """Evaluate a single issue for quality metrics."""
        uname = issue.get("_username", "unknown")
        flags = {
            "is_opened": issue.get("state") == "opened",
            "is_closed": issue.get("state") == "closed",
            "no_desc": False,
            "no_labels": False,
            "no_milestone": False,
            "no_time": False,
            "long_open_time": False,
            "no_semantic_title": False,
        }

        try:
            # 1. Description Check
            desc = issue.get("description") or ""
            if not str(desc).strip():
                flags["no_desc"] = True

            # 2. Labels Check
            labels = issue.get("labels") or []
            if not labels or len(labels) == 0:
                flags["no_labels"] = True

            # 3. Milestone Check
            milestone = issue.get("milestone")
            if not milestone:
                flags["no_milestone"] = True

            # 4. Time Spent Check
            ts = issue.get("time_stats", {})
            if isinstance(ts, dict) and ts.get("total_time_spent", 0) == 0:
                flags["no_time"] = True

            # 5. Semantic Title Check (follows conventional commits)
            title_lower = str(issue.get("title") or "").lower()
            semantic_prefixes = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "chore", "bug")
            if not any(title_lower.startswith(p) for p in semantic_prefixes):
                flags["no_semantic_title"] = True

            # 6. Long Open Time Check (issues open for more than 2 days)
            created_s = issue.get("created_at")
            closed_s = issue.get("closed_at")
            if created_s:
                created_dt = datetime.strptime(created_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                end_dt = (
                    datetime.strptime(closed_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    if closed_s
                    else datetime.now(timezone.utc)
                )
                diff = (end_dt - created_dt).total_seconds() / 86400
                if diff > 2:
                    flags["long_open_time"] = True

        except Exception:
            pass

        return uname, flags

    async def _fetch_user_issues(
        self,
        uname: str,
        project_id=None,
        group_id=None,
        issue_scope: str = "author",
    ) -> list[dict]:
        """Fetch all issues for a specific user by author or assignee scope."""
        u_data = await self._async_request("GET", "/users", params={"username": uname})
        target_user = next(
            (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(uname).lower()), None
        )
        if not target_user:
            return []
        scope = str(issue_scope or "author").strip().lower()
        if scope not in {"author", "assignee"}:
            scope = "author"

        user_filter_key = "assignee_id" if scope == "assignee" else "author_id"
        params = {user_filter_key: str(target_user["id"]), "scope": "all", "per_page": "100"}
        if project_id:
            params["project_id"] = project_id
        if group_id:
            params["group_id"] = group_id
        issues = await self._async_request("GET", "/issues", params=params)
        for issue in issues or []:
            issue["_username"] = uname
        return issues or []

    async def _batch_evaluate_issues_async(
        self,
        usernames: list[str],
        project_id=None,
        group_id=None,
        issue_scope: str = "author",
    ) -> list[dict]:
        """Batch evaluate issues for multiple users."""
        result_map = {u: {**_ZERO_ISSUE_ROW, "Username": u} for u in usernames}
        user_tasks = [self._fetch_user_issues(u, project_id, group_id, issue_scope) for u in usernames]
        all_users_issues = await asyncio.gather(*user_tasks)
        all_issues = [issue for sublist in all_users_issues for issue in sublist]
        eval_results = await asyncio.gather(*[self._evaluate_single_issue(issue) for issue in all_issues])

        for uname, f in eval_results:
            if uname in result_map:
                row = result_map[uname]
                # Count total assigned issues
                row["Total Assigned"] += 1
                
                # Count opened issues
                if f.get("is_opened"):
                    row["Opened Issues"] += 1
                
                # Count and evaluate only closed issues
                if f.get("is_closed"):
                    row["Closed Issues"] += 1
                    if f.get("no_desc"):
                        row["No Desc"] += 1
                    if f.get("no_labels"):
                        row["No Labels"] += 1
                    if f.get("no_milestone"):
                        row["No Milestone"] += 1
                    if f.get("no_time"):
                        row["No Time Spent"] += 1
                    if f.get("long_open_time"):
                        row["Long Open Time (>2 days)"] += 1
                    if f.get("no_semantic_title"):
                        row["No Semantic Title"] += 1

        return sorted(result_map.values(), key=lambda r: r["Username"])

    def batch_evaluate_issues(self, usernames, project_id=None, group_id=None, issue_scope: str = "author"):
        """Public method to batch evaluate issues for multiple users."""
        return self._run_sync(self._batch_evaluate_issues_async(usernames, project_id, group_id, issue_scope))

    def _request(self, method, endpoint, params=None):
        return self._run_sync(self._async_request(method, endpoint, params))

    def _get(self, endpoint, params=None):
        return self._request("GET", endpoint, params=params)

    def _get_paginated(self, endpoint, params=None, per_page=100, max_pages=10):
        all_items = []
        for page in range(1, max_pages + 1):
            p_params = {**(params or {}), "per_page": per_page, "page": page}
            batch = self._get(endpoint, params=p_params)
            if not isinstance(batch, list) or not batch:
                break
            all_items.extend(batch)
            if len(batch) < per_page:
                break
        return all_items

    def __del__(self):
        if self._session and not self._session.closed:
            # When using a separate thread, we can reliably close from any context
            try:
                self._run_sync(self._session.close())
                self._loop.stop()
            except Exception:
                pass
