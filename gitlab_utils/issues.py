def get_user_issues(client, user_id, since=None, until=None, project_ids=None):
    """
    Fetch Issues:
    - Authored Issues (GET /issues?author_id=:id)
    - Assigned Issues (GET /issues?assignee_id=:id)

    Optional date filters:
      since (str): ISO 8601 UTC datetime — maps to created_after
      until (str): ISO 8601 UTC datetime — maps to created_before

    Optional project filter:
      project_ids (list[int]): if provided, only issues in these projects are counted.

    Returns:
      - issues_list
      - stats: {total, opened, closed, assigned}
    """
    issues_list = []
    seen_ids = set()
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned": 0}
    pid_set = set(project_ids) if project_ids else None

    # Build optional date filter fragment added to every request
    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_and_add(base_params: dict, is_assigned: bool = False) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated("/issues", params=params, per_page=50, max_pages=10)

            for item in items:
                # Apply project filter if specified
                if pid_set is not None and item.get("project_id") not in pid_set:
                    continue

                if item["id"] not in seen_ids:
                    state = item.get("state")
                    issues_list.append(
                        {
                            "title": item.get("title"),
                            "project_id": item.get("project_id"),
                            "web_url": item.get("web_url"),
                            "state": state,
                            "created_at": item.get("created_at"),
                            "closed_at": item.get("closed_at"),
                            "assigned": is_assigned,
                        }
                    )
                    seen_ids.add(item["id"])

                    stats["total"] += 1
                    if state == "opened":
                        stats["opened"] += 1
                    elif state == "closed":
                        stats["closed"] += 1

                if is_assigned:
                    stats["assigned"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_and_add({"author_id": user_id, "scope": "all"}, is_assigned=False)

    # 2. Assigned
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, is_assigned=True)

    return issues_list, stats
