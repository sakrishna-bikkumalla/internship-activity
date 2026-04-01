from gitlab_utils.description_quality import analyze_description


def get_user_mrs(client, user_id, since=None, until=None, project_ids=None):
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
                            "project_id": item.get("project_id"),
                            "web_url": item.get("web_url"),
                            "state": state,
                            "created_at": item.get("created_at"),
                            "merged_at": item.get("merged_at"),
                            "closed_at": item.get("closed_at"),
                            "role": role_label,
                            "desc_score": desc_quality["description_score"],
                            "quality": desc_quality["quality_label"],
                            "feedback": desc_quality["feedback"],
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
    Fetch live MR compliance metrics using correct GitLab API endpoints for the selected user.
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

    if not client.client:
        return stats, problematic_mrs

    for pid in project_ids:
        try:
            project = client.client.projects.get(pid)
            mrs = project.mergerequests.list(all=True)
            for cached_mr in mrs:
                if cached_mr.author["name"] != selected_user_name:
                    continue

                try:
                    # Refresh full MR data
                    mr = project.mergerequests.get(cached_mr.iid)

                    no_desc = False
                    failed_pipeline = False
                    no_issues = False
                    no_time_spent = False
                    no_unit_tests = False

                    # a) No Description & Description Quality
                    desc_quality = analyze_description(mr.description)
                    stats["Total Desc Score"] += desc_quality["description_score"]
                    stats["Total MRs Evaluated"] += 1

                    if not mr.description or str(mr.description).strip() == "":
                        no_desc = True
                        stats["No Description"] += 1

                    # b) Failed Pipelines — use head_pipeline attribute
                    head_pipe = getattr(mr, "head_pipeline", None)
                    if head_pipe and isinstance(head_pipe, dict):
                        if head_pipe.get("status") == "failed":
                            failed_pipeline = True
                            stats["Failed Pipelines"] += 1

                    # c) No Time Spent — use time_stats API
                    try:
                        ts = mr.time_stats()
                        if not ts or ts.get("total_time_spent", 0) == 0:
                            no_time_spent = True
                            stats["No Time Spent"] += 1
                    except Exception:
                        no_time_spent = True
                        stats["No Time Spent"] += 1

                    # d) No Issues Linked — use mr.references (better than "#" string matching)
                    try:
                        refs = getattr(mr, "references", None)
                        if not refs or not refs.get("full"):
                            no_issues = True
                            stats["No Issues Linked"] += 1
                    except Exception:
                        no_issues = True
                        stats["No Issues Linked"] += 1

                    # e) No Unit Tests — use mr.changes() to inspect file paths
                    try:
                        changes_data = mr.changes()
                        changed_files = changes_data.get("changes", []) if isinstance(changes_data, dict) else []
                        has_tests = any(
                            "test" in str(ch.get("new_path", "")).lower()
                            or "spec" in str(ch.get("new_path", "")).lower()
                            for ch in changed_files
                        )
                        if not has_tests:
                            no_unit_tests = True
                            stats["No Unit Tests"] += 1
                    except Exception:
                        no_unit_tests = True
                        stats["No Unit Tests"] += 1

                    # Collect problematic MRs
                    if no_desc or failed_pipeline or no_issues or no_time_spent or no_unit_tests:
                        problematic_mrs.append(
                            {
                                "Title": mr.title,
                                "State": mr.state,
                                "No Description": no_desc,
                                "No Time Spent": no_time_spent,
                                "No Issues Linked": no_issues,
                                "No Unit Tests": no_unit_tests,
                                "Failed Pipeline": failed_pipeline,
                            }
                        )

                except Exception:
                    pass

        except Exception:
            pass

    return stats, problematic_mrs
