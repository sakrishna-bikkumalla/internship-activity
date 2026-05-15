import asyncio
import logging

from internship_activity_tracker.infrastructure.gitlab.graphql_client import _parse_gid
from internship_activity_tracker.infrastructure.gitlab.graphql_queries import (
    GQL_USER_ISSUES_ASSIGNED,
    GQL_USER_ISSUES_AUTHORED,
)

logger = logging.getLogger(__name__)


async def get_user_issues_graphql(
    client,
    username: str,
    since: str | None = None,
    until: str | None = None,
    project_ids: list | None = None,
) -> tuple[list[dict], dict]:
    """
    Fetch authored + assigned issues via GraphQL (~2 parallel queries).
    Returns (issues_list, stats) matching get_user_issues_async() shape exactly.
    """
    gql = client._gql
    if not gql:
        raise RuntimeError("GraphQL client not available")

    issues_dict: dict[int, dict] = {}
    pid_set = set(project_ids) if project_ids else None
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned": 0}

    def _node_to_issue(node: dict, role: str, is_assigned: bool) -> tuple[int, dict]:
        issue_int_id = _parse_gid(node.get("id")) or 0
        project_int_id = _parse_gid(node.get("projectId"))
        state = node.get("state") or ""
        labels = [n["title"] for n in (node.get("labels") or {}).get("nodes", [])]
        milestone = {"title": node["milestone"]["title"]} if node.get("milestone") else None
        time_spent = node.get("totalTimeSpent") or 0
        return issue_int_id, {
            "id": issue_int_id,
            "iid": node.get("iid"),
            "title": node.get("title"),
            "description": node.get("description"),
            "project_id": project_int_id,
            "web_url": node.get("webUrl"),
            "state": state,
            "created_at": node.get("createdAt"),
            "closed_at": node.get("closedAt"),
            "assigned": is_assigned,
            "role": role,
            "labels": labels,
            "milestone": milestone,
            "time_stats": {"total_time_spent": time_spent},
            "_username": username,
        }

    async def _paginate_authored() -> None:
        after = None
        while True:
            data = await gql.query(GQL_USER_ISSUES_AUTHORED, {"username": username, "after": after})
            conn = data.get("issues") or {}
            for node in conn.get("nodes") or []:
                iid, issue = _node_to_issue(node, "Author", False)
                if pid_set is not None and issue["project_id"] not in pid_set:
                    continue
                if iid in issues_dict:
                    if issues_dict[iid]["role"] == "Assigned":
                        issues_dict[iid]["role"] = "Authored & Assigned"
                else:
                    issues_dict[iid] = issue
                    stats["total"] += 1
                    if issue["state"] == "opened":
                        stats["opened"] += 1
                    elif issue["state"] == "closed":
                        stats["closed"] += 1
            pi = conn.get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                break
            after = pi["endCursor"]

    async def _paginate_assigned() -> None:
        after = None
        while True:
            data = await gql.query(GQL_USER_ISSUES_ASSIGNED, {"username": username, "after": after})
            conn = data.get("issues") or {}
            for node in conn.get("nodes") or []:
                iid, issue = _node_to_issue(node, "Assigned", True)
                if pid_set is not None and issue["project_id"] not in pid_set:
                    continue
                stats["assigned"] += 1
                if iid in issues_dict:
                    if issues_dict[iid]["role"] == "Author":
                        issues_dict[iid]["role"] = "Authored & Assigned"
                else:
                    issues_dict[iid] = issue
                    stats["total"] += 1
                    if issue["state"] == "opened":
                        stats["opened"] += 1
                    elif issue["state"] == "closed":
                        stats["closed"] += 1
            pi = conn.get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                break
            after = pi["endCursor"]

    await asyncio.gather(_paginate_authored(), _paginate_assigned())
    logger.info(f"[GraphQL/Issues] Fetched {stats['total']} issues for {username}")
    return list(issues_dict.values()), stats


async def get_user_issues_async(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Async fetch Issues. Tries GraphQL first, falls back to REST.
    """
    if client._gql and username:
        try:
            return await get_user_issues_graphql(client, username, since, until, project_ids)
        except Exception as exc:
            logger.warning(f"[GraphQL/Issues] Fast path failed, falling back to REST: {exc}")

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
