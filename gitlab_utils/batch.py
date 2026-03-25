import asyncio
import concurrent.futures

from gitlab_utils import commits, groups, issues, merge_requests, projects, users


def resolve_project_paths(client, repo_paths: list[str]) -> tuple[list[int], list[str]]:
    """
    Resolve a list of GitLab project paths (e.g. 'group/repo') to project IDs.
    Returns (resolved_ids, failed_paths).
    """
    resolved_ids: list[int] = []
    failed: list[str] = []
    for path in repo_paths:
        path = path.strip()
        if not path:
            continue
        try:
            # URL-encode the path for the API
            encoded = path.replace("/", "%2F")
            proj = client._get(f"/projects/{encoded}")
            if proj and isinstance(proj, dict) and "id" in proj:
                resolved_ids.append(proj["id"])
            else:
                failed.append(path)
        except Exception:
            failed.append(path)
    return resolved_ids, failed


def process_single_user(client, username, since=None, until=None, project_ids: list[int] | None = None):
    """
    Worker function to process a single user.
    Refactored to fetch all components (projects, groups, MRs, issues, commits)
    concurrently where possible.
    """
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
        result["data"]["user"] = user_obj

        # Use ThreadPoolExecutor for concurrent fetching
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Kick off independent fetches
            f_projs = executor.submit(projects.get_user_projects, client, user_id, username)
            f_groups = executor.submit(groups.get_user_groups, client, user_id)
            f_mrs = executor.submit(
                merge_requests.get_user_mrs, client, user_id, since=since, until=until, project_ids=project_ids
            )
            f_issues = executor.submit(
                issues.get_user_issues, client, user_id, since=since, until=until, project_ids=project_ids
            )

            # Wait for projects to resolve commit targets
            projs = f_projs.result()
            result["data"]["projects"] = projs

            # Resolve the list of projects to scan for commits
            if project_ids is not None:
                pid_set = set(project_ids)
                all_projs_list = [p for p in projs["all"] if p.get("id") in pid_set]
                existing_ids = {p.get("id") for p in all_projs_list}
                for pid in project_ids:
                    if pid not in existing_ids:
                        try:
                            p_extra = client._get(f"/projects/{pid}", params={"simple": "true"})
                            if p_extra and isinstance(p_extra, dict) and "id" in p_extra:
                                all_projs_list.append(p_extra)
                        except Exception:
                            pass
            else:
                all_projs_list = projs["all"]

            # 3. Commits (Start after projects list is ready)
            f_commits = executor.submit(
                commits.get_user_commits, client, user_obj, all_projs_list, since=since, until=until
            )

            # Gather final results
            all_commits, commit_counts, commit_stats = f_commits.result()
            user_groups = f_groups.result()
            user_mrs, mr_stats = f_mrs.result()
            user_issues, issue_stats = f_issues.result()

        # Populate result data
        result["data"]["commits"] = all_commits
        result["data"]["commit_stats"] = commit_stats
        result["data"]["groups"] = user_groups
        result["data"]["mrs"] = user_mrs
        result["data"]["mr_stats"] = mr_stats
        result["data"]["issues"] = user_issues
        result["data"]["issue_stats"] = issue_stats

        # Refine Contributed projects display - only those with verified commits
        result["data"]["projects"]["contributed"] = [
            p for p in projs["contributed"] if p["id"] in commit_counts and commit_counts[p["id"]] > 0
        ]

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)

    return result


def process_batch_users(client, usernames, since=None, until=None, project_ids: list[int] | None = None):
    """
    Concurrent processing of multiple users using ThreadPoolExecutor.
    Safe to call from Streamlit.
    """
    results = []
    clean_usernames = [u.strip() for u in usernames if u.strip()]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_user = {
            executor.submit(process_single_user, client, u, since, until, project_ids): u for u in clean_usernames
        }
        for future in concurrent.futures.as_completed(future_to_user):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as exc:
                u = future_to_user[future]
                results.append({"username": u, "status": "Crash", "error": str(exc)})

    return results


async def process_batch_users_async(client, usernames, since=None, until=None, project_ids: list[int] | None = None):
    """
    Async version for non-Streamlit contexts.
    """
    clean_usernames = [u.strip() for u in usernames if u.strip()]

    async def _safe_single(uname: str):
        try:
            result = await asyncio.to_thread(process_single_user, client, uname, since, until, project_ids)
            return result
        except Exception as exc:
            return {"username": uname, "status": "Crash", "error": str(exc)}

    all_results = await asyncio.gather(*[_safe_single(u) for u in clean_usernames])
    return [r for r in all_results if r is not None]
