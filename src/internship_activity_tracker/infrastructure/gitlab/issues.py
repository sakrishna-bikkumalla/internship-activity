import asyncio


async def get_user_issues_async(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Async fetch Issues.
    """
    issues_dict = {}
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned": 0}
    pid_set = set(project_ids) if project_ids else None

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    # Run authored and assigned fetches concurrently
    authored_f = client._async_get_paginated(
        "/issues", params={"author_id": user_id, "scope": "all", **date_params}, per_page=100
    )
    assigned_f = client._async_get_paginated(
        "/issues", params={"assignee_id": user_id, "scope": "all", **date_params}, per_page=100
    )

    authored_items, assigned_items = await asyncio.gather(authored_f, assigned_f)

    for items, is_assigned, role_label in [(authored_items, False, "Author"), (assigned_items, True, "Assigned")]:
        for item in items:
            if pid_set is not None and item.get("project_id") not in pid_set:
                continue

            if item["id"] in issues_dict:
                existing_role = issues_dict[item["id"]]["role"]
                if existing_role != role_label and existing_role != "Authored & Assigned":
                    issues_dict[item["id"]]["role"] = "Authored & Assigned"
            else:
                state = item.get("state")
                issues_dict[item["id"]] = {
                    "id": item["id"],
                    "iid": item.get("iid"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "project_id": item.get("project_id"),
                    "web_url": item.get("web_url"),
                    "state": state,
                    "created_at": item.get("created_at"),
                    "closed_at": item.get("closed_at"),
                    "assigned": is_assigned,
                    "role": role_label,
                    "labels": item.get("labels", []),
                    "milestone": item.get("milestone"),
                    "time_stats": item.get("time_stats", {}),
                    "_username": username,
                }
                stats["total"] += 1
                if state == "opened":
                    stats["opened"] += 1
                elif state == "closed":
                    stats["closed"] += 1

            if is_assigned:
                stats["assigned"] += 1

    return list(issues_dict.values()), stats


def get_user_issues(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Fetch Issues:
    - Authored Issues (GET /issues?author_id=:id)
    - Assigned Issues (GET /issues?assignee_id=:id)

    Returns:
      - issues_list
      - stats: {total, opened, closed, assigned}
    """
    issues_dict = {}
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned": 0}
    pid_set = set(project_ids) if project_ids else None

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_and_add(base_params: dict, is_assigned: bool = False, role_label: str = "Author") -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated("/issues", params=params, per_page=50, max_pages=10)

            for item in items:
                if pid_set is not None and item.get("project_id") not in pid_set:
                    continue

                if item["id"] in issues_dict:
                    existing_role = issues_dict[item["id"]]["role"]
                    if existing_role != role_label and existing_role != "Authored & Assigned":
                        issues_dict[item["id"]]["role"] = "Authored & Assigned"
                else:
                    state = item.get("state")
                    issues_dict[item["id"]] = {
                        "id": item["id"],
                        "iid": item.get("iid"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "project_id": item.get("project_id"),
                        "web_url": item.get("web_url"),
                        "state": state,
                        "created_at": item.get("created_at"),
                        "closed_at": item.get("closed_at"),
                        "assigned": is_assigned,
                        "role": role_label,
                        "labels": item.get("labels", []),
                        "milestone": item.get("milestone"),
                        "time_stats": item.get("time_stats", {}),
                        "_username": username,
                    }

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
    fetch_and_add({"author_id": user_id, "scope": "all"}, is_assigned=False, role_label="Author")
    # 2. Assigned
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, is_assigned=True, role_label="Assigned")

    return list(issues_dict.values()), stats
