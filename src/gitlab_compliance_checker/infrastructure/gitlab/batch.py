import asyncio
import atexit
import concurrent.futures

from gitlab_compliance_checker.infrastructure.gitlab import commits, groups, issues, merge_requests, projects, users

# Global Thread Pool to limit total concurrent network operations across the app
# This prevents "Connection Reset" errors when scanning multiple teams
_GLOBAL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)
atexit.register(lambda: _GLOBAL_EXECUTOR.shutdown(wait=False))


def resolve_project_paths(client, repo_paths: list[str]) -> tuple[list[int], list[str]]:
    """
    Resolve a list of GitLab project paths (e.g. 'group/repo') to project IDs in parallel.
    Returns (resolved_ids, failed_paths).
    """
    resolved_ids: list[int] = []
    failed: list[str] = []
    clean_paths = [p.strip() for p in repo_paths if p.strip()]

    if not clean_paths:
        return [], []

    def _resolve_one(path):
        try:
            # URL-encode the path for the API
            encoded = path.replace("/", "%2F")
            proj = client._get(f"/projects/{encoded}")
            if proj and isinstance(proj, dict) and "id" in proj:
                return proj["id"], None
            else:
                return None, path
        except Exception:
            return None, path

    results = list(_GLOBAL_EXECUTOR.map(_resolve_one, clean_paths))

    for rid, fpath in results:
        if rid:
            resolved_ids.append(rid)
        if fpath:
            failed.append(fpath)

    return resolved_ids, failed


def process_single_user(
    client,
    username,
    since=None,
    until=None,
    project_ids: list[int] | None = None,
    override_email: str | None = None,
    override_username: str | None = None,
    time_since: str | None = None,
    time_until: str | None = None,
):
    """
    Worker function to process a single user.
    Refactored to fetch all components (projects, groups, MRs, issues, commits, timelogs)
    concurrently where possible.
    """
    from datetime import date

    from gitlab_compliance_checker.infrastructure.gitlab.timelogs import (
        aggregate_daily_time,
        build_daily_time_from_time_stats,
        fetch_user_timelogs_from_projects,
    )

    username = username.strip()
    result = {"username": username, "status": "Success", "error": None, "data": {}}

    if not username:
        return None

    try:
        # 1. Get User (Foundation)
        user_obj = users.get_user_by_username(client, username)
        if not user_obj:
            result["status"] = "Not Found"
            result["error"] = "User not found"
            return result

        user_id = user_obj["id"]
        if override_email:
            user_obj["override_email"] = override_email
        if override_username:
            user_obj["override_username"] = override_username
        result["data"]["user"] = user_obj

        # Use global executor for concurrent fetching
        f_projs = _GLOBAL_EXECUTOR.submit(projects.get_user_projects, client, user_id, username)
        f_groups = _GLOBAL_EXECUTOR.submit(groups.get_user_groups, client, user_id)
        f_mrs = _GLOBAL_EXECUTOR.submit(
            merge_requests.get_user_mrs,
            client,
            user_id,
            username=username,
            since=since,
            until=until,
            project_ids=project_ids,
        )
        f_issues = _GLOBAL_EXECUTOR.submit(
            issues.get_user_issues,
            client,
            user_id,
            username=username,
            since=since,
            until=until,
            project_ids=project_ids,
        )

        # Wait for projects to resolve commit targets
        projs = f_projs.result()
        result["data"]["projects"] = projs

        # Resolve the list of projects to scan for commits
        all_projs_dict = {p.get("id"): p for p in projs["all"]}

        if project_ids is not None:
            pid_set = set(project_ids)
            all_projs_list = [p for p in all_projs_dict.values() if p.get("id") in pid_set]
            existing_ids = {p.get("id") for p in all_projs_list}

            # Fetch details for project_ids that weren't in the user's projects list
            for pid in project_ids:
                if pid not in existing_ids:
                    try:
                        p_extra = client._get(f"/projects/{pid}", params={"simple": "true"})
                        if p_extra and isinstance(p_extra, dict) and "id" in p_extra:
                            all_projs_list.append(p_extra)
                    except Exception:
                        pass
        else:
            all_projs_list = list(all_projs_dict.values())

        # 3. Commits (Start after projects list is ready)
        f_commits = _GLOBAL_EXECUTOR.submit(
            commits.get_user_commits, client, user_obj, all_projs_list, since=since, until=until
        )

        # Gather final results
        all_commits, commit_counts, commit_stats = f_commits.result()
        user_groups = f_groups.result()
        user_mrs, mr_stats = f_mrs.result()
        user_issues, issue_stats = f_issues.result()

        # 4. Timelogs (Special handling for Leaderboard all-time spent)
        def _to_date(val, default):
            if not val:
                return default
            if isinstance(val, date):
                return val
            try:
                # Handle ISO strings (strip time if present)
                return date.fromisoformat(str(val)[:10])
            except Exception:
                return default

        t_since = _to_date(time_since, _to_date(since, date(2000, 1, 1)))
        t_until = _to_date(time_until, _to_date(until, date.today()))

        total_time_spent = 0
        try:
            # Discover projects from MRs/Issues to ensure no project is missed
            timelog_projs = list(all_projs_list)
            seen_t_pids = {p.get("id") for p in timelog_projs if p.get("id")}
            for item in user_mrs + user_issues:
                pid = item.get("project_id")
                if pid and pid not in seen_t_pids:
                    timelog_projs.append({"id": pid})
                    seen_t_pids.add(pid)

            timelogs_raw = fetch_user_timelogs_from_projects(client, user_id, timelog_projs, t_since, t_until)
            daily_times = aggregate_daily_time(timelogs_raw)

            # Supplement with time_stats fallback
            daily_times = build_daily_time_from_time_stats(
                user_issues,
                user_mrs,
                client,
                t_since.isoformat(),
                t_until.isoformat(),
                existing_daily_times=daily_times,
            )
            total_time_spent = sum(daily_times.values())
        except Exception as te:
            # Don't crash the whole user if timelogs fail
            import logging

            logging.getLogger(__name__).error(f"Timelog fetch failed for {username}: {te}")

        # 5. Quality Evaluation (Efficient)
        authored_issues = [i for i in user_issues if i.get("role") == "Author"]
        authored_mrs = [m for m in user_mrs if m.get("role") == "Authored"]

        issue_quality = client.batch_evaluate_issues_efficiently(authored_issues)
        mr_quality = client.batch_evaluate_mrs_efficiently(authored_mrs)

        # Populate result data
        result["data"]["commits"] = all_commits
        result["data"]["commit_stats"] = commit_stats
        result["data"]["groups"] = user_groups
        result["data"]["mrs"] = user_mrs
        result["data"]["mr_stats"] = mr_stats
        result["data"]["issues"] = user_issues
        result["data"]["issue_stats"] = issue_stats
        result["data"]["issue_quality"] = issue_quality
        result["data"]["mr_quality"] = mr_quality
        result["data"]["total_time_spent_seconds"] = total_time_spent

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)

    return result


def process_batch_users(
    client, usernames, since=None, until=None, project_ids: list[int] | None = None, overrides: dict | None = None
):
    """
    Concurrent processing of multiple users using ThreadPoolExecutor.
    Safe to call from Streamlit.
    """
    results = []
    clean_usernames = [u.strip() for u in usernames if u.strip()]

    future_to_user = {}
    for u in clean_usernames:
        ov = overrides.get(u, {}) if overrides else {}
        future = _GLOBAL_EXECUTOR.submit(process_single_user, client, u, since, until, project_ids, **ov)
        future_to_user[future] = u
    for future in concurrent.futures.as_completed(future_to_user):
        try:
            res = future.result()
            if res:
                results.append(res)
        except Exception as exc:
            u = future_to_user[future]
            results.append({"username": u, "status": "Crash", "error": str(exc)})

    return results


async def resolve_project_paths_async(client, repo_paths: list[str]) -> tuple[list[int], list[str]]:
    """
    Async resolve a list of GitLab project paths to project IDs.
    """
    clean_paths = [p.strip() for p in repo_paths if p.strip()]
    if not clean_paths:
        return [], []

    async def _resolve_one(path):
        try:
            encoded = path.replace("/", "%2F")
            proj = await client._async_get(f"/projects/{encoded}")
            if proj and isinstance(proj, dict) and "id" in proj:
                return proj["id"], None
            return None, path
        except Exception:
            return None, path

    results = await asyncio.gather(*[_resolve_one(p) for p in clean_paths])

    resolved_ids = [rid for rid, fpath in results if rid]
    failed = [fpath for rid, fpath in results if fpath]
    return resolved_ids, failed


async def process_single_user_async(
    client,
    username,
    since=None,
    until=None,
    project_ids: list[int] | None = None,
    override_email: str | None = None,
    override_username: str | None = None,
    time_since: str | None = None,
    time_until: str | None = None,
):
    """
    Async worker to process a single user with maximum concurrency.
    """
    from datetime import date

    from gitlab_compliance_checker.infrastructure.gitlab.timelogs import (
        aggregate_daily_time,
        build_daily_time_from_time_stats,
        fetch_user_timelogs_from_projects_async,
    )

    username = username.strip()
    result = {"username": username, "status": "Success", "error": None, "data": {}}

    if not username:
        return None

    try:
        # 1. Get User (Foundation)
        user_obj = await users.get_user_by_username_async(client, username)
        if not user_obj:
            result["status"] = "Not Found"
            result["error"] = "User not found"
            return result

        user_id = user_obj["id"]
        if override_email:
            user_obj["override_email"] = override_email
        if override_username:
            user_obj["override_username"] = override_username
        result["data"]["user"] = user_obj

        # 2. Concurrent Fetching (Components that only need user_id)
        f_projs = projects.get_user_projects_async(client, user_id, username)
        f_groups = groups.get_user_groups_async(client, user_id)
        f_mrs = merge_requests.get_user_mrs_async(
            client, user_id, username=username, since=since, until=until, project_ids=project_ids
        )
        f_issues = issues.get_user_issues_async(
            client, user_id, username=username, since=since, until=until, project_ids=project_ids
        )

        # Gather these foundation components
        projs, user_groups, (user_mrs, mr_stats), (user_issues, issue_stats) = await asyncio.gather(
            f_projs, f_groups, f_mrs, f_issues
        )

        # 3. Resolve projects for commits
        all_projs_dict = {p.get("id"): p for p in projs["all"]}
        if project_ids is not None:
            pid_set = set(project_ids)
            all_projs_list = [p for p in all_projs_dict.values() if p.get("id") in pid_set]
            existing_ids = {p.get("id") for p in all_projs_list}

            missing_pids = [pid for pid in project_ids if pid not in existing_ids]
            if missing_pids:
                extra_f = [client._async_get(f"/projects/{pid}", params={"simple": "true"}) for pid in missing_pids]
                extra_projects = await asyncio.gather(*extra_f)
                for p_extra in extra_projects:
                    if p_extra and isinstance(p_extra, dict) and "id" in p_extra:
                        all_projs_list.append(p_extra)
        else:
            all_projs_list = list(all_projs_dict.values())

        # 4. Fetch Commits
        all_commits, commit_counts, commit_stats = await commits.get_user_commits_async(
            client, user_obj, all_projs_list, since=since, until=until
        )

        # 5. Timelogs (Special handling for Leaderboard all-time spent)
        def _to_date(val, default):
            if not val:
                return default
            if isinstance(val, date):
                return val
            try:
                return date.fromisoformat(str(val)[:10])
            except Exception:
                return default

        t_since = _to_date(time_since, _to_date(since, date(2000, 1, 1)))
        t_until = _to_date(time_until, _to_date(until, date.today()))

        total_time_spent = 0
        try:
            timelog_projs = list(all_projs_list)
            seen_t_pids = {p.get("id") for p in timelog_projs if p.get("id")}
            for item in user_mrs + user_issues:
                pid = item.get("project_id")
                if pid and pid not in seen_t_pids:
                    timelog_projs.append({"id": pid})
                    seen_t_pids.add(pid)

            timelogs_raw = await fetch_user_timelogs_from_projects_async(
                client, user_id, timelog_projs, t_since, t_until
            )
            daily_times = aggregate_daily_time(timelogs_raw)

            # Supplement with time_stats fallback
            daily_times = build_daily_time_from_time_stats(
                user_issues,
                user_mrs,
                client,
                t_since.isoformat(),
                t_until.isoformat(),
                existing_daily_times=daily_times,
            )
            total_time_spent = sum(daily_times.values())
        except Exception as te:
            import logging

            logging.getLogger(__name__).error(f"Async timelog fetch failed for {username}: {te}")

        # 6. Quality Evaluation (Efficient logic, already async-friendly)
        authored_issues = [i for i in user_issues if i.get("role") == "Author"]
        authored_mrs = [m for m in user_mrs if m.get("role") == "Authored"]

        issue_quality = client.batch_evaluate_issues_efficiently(authored_issues)
        mr_quality = client.batch_evaluate_mrs_efficiently(authored_mrs)

        # Populate result data
        result["data"].update(
            {
                "projects": projs,
                "commits": all_commits,
                "commit_stats": commit_stats,
                "groups": user_groups,
                "mrs": user_mrs,
                "mr_stats": mr_stats,
                "issues": user_issues,
                "issue_stats": issue_stats,
                "issue_quality": issue_quality,
                "mr_quality": mr_quality,
                "total_time_spent_seconds": total_time_spent,
            }
        )

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)

    return result


async def process_batch_users_async(
    client, usernames, since=None, until=None, project_ids: list[int] | None = None, overrides: dict | None = None
):
    """
    Core async batch processing with maximum concurrency.
    Handles exceptions by returning a "Crash" status for the specific user.
    """
    clean_usernames = [u.strip() for u in usernames if u.strip()]
    if not clean_usernames:
        return []

    async def _safe_process(u):
        try:
            ov = overrides.get(u, {}) if overrides else {}
            res = await process_single_user_async(client, u, since, until, project_ids, **ov)
            return res
        except Exception as exc:
            return {"username": u, "status": "Crash", "error": str(exc)}

    results = await asyncio.gather(*[_safe_process(u) for u in clean_usernames])
    return [r for r in results if r is not None]
