import asyncio
import logging

from internship_activity_tracker.infrastructure.gitlab.description_quality import analyze_description
from internship_activity_tracker.infrastructure.gitlab.graphql_client import _parse_gid
from internship_activity_tracker.infrastructure.gitlab.graphql_queries import (
    GQL_USER_MRS_ASSIGNED,
    GQL_USER_MRS_AUTHORED,
)

logger = logging.getLogger(__name__)


def _mr_node_to_dict(node: dict, role: str, username: str | None) -> tuple[int, dict]:
    """Normalize a GraphQL MR node into the standard MR dict shape. Returns (int_id, mr_dict)."""

    mr_int_id = _parse_gid(node.get("id")) or 0
    project_int_id = _parse_gid((node.get("project") or {}).get("id"))
    state = node.get("state") or ""
    desc = node.get("description") or ""
    desc_quality = analyze_description(desc)

    pipeline = node.get("headPipeline")
    head_pipeline = {"status": pipeline["status"]} if pipeline else None
    time_spent = node.get("totalTimeSpent") or 0

    # Store commit messages for Phase 4 inline evaluation
    commit_nodes = (node.get("commits") or {}).get("nodes") or []
    commit_msgs = [c.get("title", "") or "" for c in commit_nodes]

    return mr_int_id, {
        "id": mr_int_id,
        "iid": node.get("iid"),
        "title": node.get("title"),
        "description": desc,
        "project_id": project_int_id,
        "project_path": (node.get("project") or {}).get("fullPath"),
        "web_url": node.get("webUrl"),
        "state": state,
        "created_at": node.get("createdAt"),
        "merged_at": node.get("mergedAt"),
        "closed_at": node.get("closedAt"),
        "role": role,
        "upvotes": node.get("upvotes") or 0,
        "user_notes_count": node.get("userNotesCount") or 0,
        "time_stats": {"total_time_spent": time_spent},
        "head_pipeline": head_pipeline,
        "desc_score": desc_quality["description_score"],
        "quality": desc_quality["quality_label"],
        "feedback": desc_quality["feedback"],
        "_username": username,
        "_commit_msgs": commit_msgs,  # used by Phase 4 inline evaluation
    }


async def get_user_mrs_graphql(
    client,
    username: str,
    since: str | None = None,
    until: str | None = None,
    project_ids: list | None = None,
) -> tuple[list[dict], dict]:
    """
    Fetch authored + assigned MRs via GraphQL (~2 paginated queries instead of 2+ REST pages each).
    Returns (mrs_list, stats) with the exact same shape as get_user_mrs_async().
    """
    gql = client._gql
    if not gql:
        raise RuntimeError("GraphQL client not available")

    mrs_dict: dict[int, dict] = {}
    pid_set = set(project_ids) if project_ids else None
    stats = {"total": 0, "merged": 0, "closed": 0, "opened": 0, "pending": 0, "assigned": 0}

    async def _paginate_authored() -> None:
        after = None
        while True:
            data = await gql.query(GQL_USER_MRS_AUTHORED, {"username": username, "after": after})
            conn = ((data.get("user") or {}).get("authoredMergeRequests")) or {}
            for node in conn.get("nodes") or []:
                mr_int_id, mr = _mr_node_to_dict(node, "Authored", username)
                if pid_set is not None and mr["project_id"] not in pid_set:
                    continue
                if mr_int_id in mrs_dict:
                    if mrs_dict[mr_int_id]["role"] == "Assigned":
                        mrs_dict[mr_int_id]["role"] = "Authored & Assigned"
                else:
                    mrs_dict[mr_int_id] = mr
                    stats["total"] += 1
                    state = mr["state"]
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1
            pi = conn.get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                break
            after = pi["endCursor"]

    async def _paginate_assigned() -> None:
        after = None
        while True:
            data = await gql.query(GQL_USER_MRS_ASSIGNED, {"username": username, "after": after})
            conn = ((data.get("user") or {}).get("assignedMergeRequests")) or {}
            for node in conn.get("nodes") or []:
                mr_int_id, mr = _mr_node_to_dict(node, "Assigned", username)
                if pid_set is not None and mr["project_id"] not in pid_set:
                    continue
                stats["assigned"] += 1
                if mr_int_id in mrs_dict:
                    if mrs_dict[mr_int_id]["role"] == "Authored":
                        mrs_dict[mr_int_id]["role"] = "Authored & Assigned"
                else:
                    mrs_dict[mr_int_id] = mr
                    stats["total"] += 1
                    state = mr["state"]
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1
            pi = conn.get("pageInfo") or {}
            if not pi.get("hasNextPage"):
                break
            after = pi["endCursor"]

    await asyncio.gather(_paginate_authored(), _paginate_assigned())
    logger.info(f"[GraphQL/MRs] Fetched {stats['total']} MRs for {username}")
    return list(mrs_dict.values()), stats


async def get_user_mrs_async(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Async fetch Merge Requests. Tries GraphQL first, falls back to REST.
    """
    if client._gql and username:
        try:
            return await get_user_mrs_graphql(client, username, since, until, project_ids)
        except Exception as exc:
            logger.warning(f"[GraphQL/MRs] Fast path failed, falling back to REST: {exc}")

    mrs_dict = {}
    pid_set = set(project_ids) if project_ids else None

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0,
        "pending": 0,
        "assigned": 0,
    }

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    # Run authored and assigned fetches concurrently
    authored_f = client._async_get_paginated(
        "/merge_requests", params={"author_id": user_id, "scope": "all", **date_params}, per_page=100
    )
    assigned_f = client._async_get_paginated(
        "/merge_requests", params={"assignee_id": user_id, "scope": "all", **date_params}, per_page=100
    )

    authored_items, assigned_items = await asyncio.gather(authored_f, assigned_f)

    for items, role_label in [(authored_items, "Authored"), (assigned_items, "Assigned")]:
        for item in items:
            if pid_set is not None and item.get("project_id") not in pid_set:
                continue

            if role_label == "Assigned":
                stats["assigned"] += 1

            if item["id"] in mrs_dict:
                existing_role = mrs_dict[item["id"]]["role"]
                if existing_role != role_label and existing_role != "Authored & Assigned":
                    mrs_dict[item["id"]]["role"] = "Authored & Assigned"
            else:
                state = item.get("state")
                desc_quality = analyze_description(item.get("description", ""))
                mrs_dict[item["id"]] = {
                    "id": item["id"],
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
                stats["total"] += 1
                if state == "merged":
                    stats["merged"] += 1
                elif state == "closed":
                    stats["closed"] += 1
                elif state == "opened":
                    stats["opened"] += 1
                    stats["pending"] += 1

    return list(mrs_dict.values()), stats


def get_user_mrs(client, user_id, username=None, since=None, until=None, project_ids=None):
    """
    Fetch Merge Requests:
    - Authored MRs (GET /merge_requests?author_id=:id)
    - Assigned MRs (GET /merge_requests?assignee_id=:id)

    Returns:
      - mrs_list: List of MR dicts
      - stats: Dict {total, merged, closed, opened, pending, assigned}
    """
    mrs_dict = {}
    pid_set = set(project_ids) if project_ids else None

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0,
        "pending": 0,
        "assigned": 0,
    }

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
                if pid_set is not None and item.get("project_id") not in pid_set:
                    continue

                if role_label == "Assigned":
                    stats["assigned"] += 1

                if item["id"] in mrs_dict:
                    existing_role = mrs_dict[item["id"]]["role"]
                    if existing_role != role_label and existing_role != "Authored & Assigned":
                        mrs_dict[item["id"]]["role"] = "Authored & Assigned"
                else:
                    state = item.get("state")
                    desc_quality = analyze_description(item.get("description", ""))
                    mrs_dict[item["id"]] = {
                        "id": item["id"],
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

    return list(mrs_dict.values()), stats


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
