import asyncio

from gitlab_compliance_checker.infrastructure.gitlab.description_quality import analyze_description


def get_user_mrs(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Fetch Merge Requests:
    - Authored MRs (GET /merge_requests?author_id=:id)
    - Assigned MRs (GET /merge_requests?assignee_id=:id)

    Optional date filters:
      since (str): ISO 8601 UTC datetime — maps to created_after
      until (str): ISO 8601 UTC datetime — maps to created_before

    Optional project filter:
      project_ids (list[int]): if provided, only MRs in these projects are counted.

    Returns:
      - mrs_list: List of MR dicts
      - stats: Dict {total, merged, closed, opened, pending, assigned}
    """
    mrs_list = []
    seen_ids = set()
    pid_set = set(project_ids) if project_ids else None

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0,
        "pending": 0,
        "assigned": 0,
    }

    # Build optional date filter fragment added to every request
    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_and_add(base_params: dict, role_label: str) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated("/merge_requests", params=params, per_page=50, max_pages=10)
            for item in items:
                # Apply project filter if specified
                if pid_set is not None and item.get("project_id") not in pid_set:
                    continue

                if role_label == "Assigned":
                    stats["assigned"] += 1

                if item["id"] not in seen_ids:
                    state = item.get("state")

                    desc_quality = analyze_description(item.get("description", ""))
                    mrs_list.append(
                        {
                            "title": item.get("title"),
                            "description": item.get("description"),
                            "project_id": item.get("project_id"),
                            "iid": item.get("iid"),
                            "web_url": item.get("web_url"),
                            "state": state,
                            "created_at": item.get("created_at"),
                            "merged_at": item.get("merged_at"),
                            "closed_at": item.get("closed_at"),
                            "role": role_label,
                            "upvotes": item.get("upvotes", 0),
                            "user_notes_count": item.get("user_notes_count", 0),
                            "time_stats": item.get("time_stats", {}),
                            "head_pipeline": item.get("head_pipeline"),
                            "desc_score": desc_quality["description_score"],
                            "quality": desc_quality["quality_label"],
                            "feedback": desc_quality["feedback"],
                            "_username": username,
                        }
                    )
                    seen_ids.add(item["id"])

                    stats["total"] += 1
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_and_add({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, "Assigned")

    return mrs_list, stats


def get_single_user_live_mr_compliance(client, project_ids, selected_user_name):
    """
    Fetch live MR compliance metrics using efficient GitLab API queries for the selected user.
    """
    stats = {
        "No Description": 0,
        "Failed Pipelines": 0,
        "No Issues Linked": 0,
        "No Time Spent": 0,
        "No Unit Tests": 0,
        "Total Desc Score": 0,
        "Total MRs Evaluated": 0,
    }

    problematic_mrs = []

    if not client:
        return stats, problematic_mrs

    try:
        # Resolve user ID first (faster filtering)
        u_data = client._get("/users", params={"username": selected_user_name})
        target_user = next(
            (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(selected_user_name).lower()), None
        )
        if not target_user:
            return stats, problematic_mrs

        user_id = target_user["id"]

        # Fetch all authored MRs for this user across all projects (more efficient than project-by-project)
        # We can filter by project_ids later or in the request if it's small enough.
        params = {"author_id": user_id, "scope": "all", "per_page": 100}
        mrs = client._get_paginated("/merge_requests", params=params)

        pid_set = set(project_ids) if project_ids else None

        # We only care about MRs in the selected projects
        target_mrs = [mr for mr in mrs if pid_set is None or mr.get("project_id") in pid_set]

        # For detailed evaluation, we'll use the client's async evaluator
        # Note: client is the GitLabClient wrapper
        async def evaluate_all():
            try:
                if not target_mrs:
                    return []
                results = await asyncio.gather(
                    *[client._evaluate_single_mr(mr) for mr in target_mrs], return_exceptions=True
                )
                # Filter out exceptions and ensure we return a tuple for each MR
                return [(res if isinstance(res, tuple) else ("unknown", {})) for res in results]
            finally:
                pass  # The loop will close coros, but we want to ensure this object is handled.

        coro = evaluate_all()
        eval_results = []
        try:
            eval_results = client._run_sync(coro)
            # If _run_sync is a MagicMock, it returns another MagicMock which is truthy
            # but hasn't actually awaited the coro.
        except Exception:
            eval_results = []
        finally:
            # Crucial: Always try to close the coro if it was never awaited.
            # This prevents RuntimeWarning in tests where _run_sync is mocked without side_effect.
            try:
                if coro and hasattr(coro, "close"):
                    coro.close()
            except Exception:
                pass

        if eval_results and isinstance(eval_results, list) and len(eval_results) == len(target_mrs):
            for i in range(len(target_mrs)):
                mr = target_mrs[i]
                uname, f = eval_results[i]
                # Description Quality (always evaluate)
                desc = mr.get("description") or ""
                desc_quality = analyze_description(desc)
                stats["Total Desc Score"] += desc_quality["description_score"]
                stats["Total MRs Evaluated"] += 1

                no_desc = f.get("no_desc", False)
                if no_desc:
                    stats["No Description"] += 1

                failed_pipeline = f.get("failed_pipe", False)
                if failed_pipeline:
                    stats["Failed Pipelines"] += 1

                no_issues = f.get("no_issues", False)
                if no_issues:
                    stats["No Issues Linked"] += 1

                no_time_spent = f.get("no_time", False)
                if no_time_spent:
                    stats["No Time Spent"] += 1

                no_unit_tests = f.get("no_unit_tests", False)
                if no_unit_tests:
                    stats["No Unit Tests"] += 1

                # Collect problematic MRs
                if no_desc or failed_pipeline or no_issues or no_time_spent or no_unit_tests:
                    problematic_mrs.append(
                        {
                            "Title": mr.get("title"),
                            "State": mr.get("state"),
                            "No Description": no_desc,
                            "No Time Spent": no_time_spent,
                            "No Issues Linked": no_issues,
                            "No Unit Tests": no_unit_tests,
                            "Failed Pipeline": failed_pipeline,
                        }
                    )

    except Exception:
        # Fallback or log error
        pass

    return stats, problematic_mrs
