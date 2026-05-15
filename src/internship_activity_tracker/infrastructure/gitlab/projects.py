import asyncio
import logging
from urllib.parse import urlparse

from internship_activity_tracker.infrastructure.gitlab.graphql_client import _parse_gid
from internship_activity_tracker.infrastructure.gitlab.graphql_queries import GQL_USER_PROJECTS

logger = logging.getLogger(__name__)


async def get_user_projects_graphql(client, username: str) -> dict:
    """
    Fetch user projects via GraphQL — one query (contributedProjects + projectMemberships).
    Returns same {personal, contributed, all} shape as get_user_projects_async().
    """
    gql = client._gql
    if not gql:
        raise RuntimeError("GraphQL client not available")

    data = await gql.query(GQL_USER_PROJECTS, {"username": username})
    user_data = data.get("user") or {}

    def _normalize(node: dict) -> dict:
        ns = node.get("namespace") or {}
        return {
            "id": _parse_gid(node.get("id")),
            "name": node.get("name"),
            "name_with_namespace": node.get("nameWithNamespace"),
            "web_url": node.get("webUrl"),
            "namespace": {
                "path": ns.get("path"),
                "kind": "user" if ns.get("path", "").lower() == username.lower() else "group",
            },
        }

    seen_ids: set[int | None] = set()
    personal: list[dict] = []
    contributed: list[dict] = []

    # contributedProjects — classify by namespace path (kind not available in this GitLab version)
    for node in (user_data.get("contributedProjects") or {}).get("nodes") or []:
        p = _normalize(node)
        if p["id"] in seen_ids:
            continue
        seen_ids.add(p["id"])
        ns_path = (p.get("namespace") or {}).get("path") or ""
        if ns_path.lower() == username.lower():
            personal.append(p)
        else:
            contributed.append(p)

    # projectMemberships — may surface personal projects not in contributedProjects
    for node_wrapper in (user_data.get("projectMemberships") or {}).get("nodes") or []:
        node = node_wrapper.get("project") or {}
        if not node:
            continue
        p = _normalize(node)
        if p["id"] in seen_ids:
            continue
        seen_ids.add(p["id"])
        ns_path = (p.get("namespace") or {}).get("path") or ""
        if ns_path.lower() == username.lower():
            personal.append(p)
        else:
            contributed.append(p)

    all_projects = personal + contributed
    logger.info(f"[GraphQL/Projects] {len(personal)} personal, {len(contributed)} contributed for {username}")
    return {"personal": personal, "contributed": contributed, "all": all_projects}


def extract_path_from_url(input_str: str) -> str:
    """Extract project path from GitLab URL or return input as is."""
    input_str = input_str.strip()
    try:
        path = urlparse(input_str).path.strip("/")
        if path.endswith(".git"):
            return path[:-4]
        return path
    except Exception:
        return input_str


def get_project_with_retries(gl_client, path_or_id):
    """Fetch project by ID or path from gitlab client wrapper."""
    from urllib.parse import quote

    try:
        pid = int(path_or_id) if str(path_or_id).isdigit() else path_or_id
        encoded_path = quote(str(pid), safe="")
        return gl_client._get(f"/projects/{encoded_path}")
    except Exception:
        raise


async def get_user_projects_async(client, user_id, username):
    """
    Fetches all projects for a user asynchronously. Tries GraphQL first.
    """
    if client._gql and username:
        try:
            return await get_user_projects_graphql(client, username)
        except Exception as exc:
            logger.warning(f"[GraphQL/Projects] Fast path failed, falling back to REST: {exc}")
    try:
        # Step 1 & 2: Fetch projects and events concurrently
        f_projects = client._async_get_paginated(
            f"/users/{user_id}/projects",
            params={"simple": "true"},
            per_page=50,
            max_pages=10,
        )
        f_events = client._async_get_paginated(
            f"/users/{user_id}/events",
            params={},
            per_page=100,
            max_pages=5,
        )

        projects_data, events_data = await asyncio.gather(f_projects, f_events)

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p["id"] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p["id"])

        event_project_ids = set()
        for e in events_data:
            pid = e.get("project_id")
            if pid and pid not in seen_ids:
                event_project_ids.add(pid)

        # Step 3: Fetch extra project details concurrently
        if event_project_ids:
            extra_f = [client._async_get(f"/projects/{pid}", params={"simple": "true"}) for pid in event_project_ids]
            extra_projects = await asyncio.gather(*extra_f)
            for p_extra in extra_projects:
                if p_extra and isinstance(p_extra, dict) and "id" in p_extra:
                    if p_extra["id"] not in seen_ids:
                        unique_projects.append(p_extra)
                        seen_ids.add(p_extra["id"])

        personal = []
        contributed = []

        for p in unique_projects:
            namespace = p.get("namespace", {})
            ns_path = namespace.get("path")
            ns_kind = namespace.get("kind")

            if ns_kind == "user" and str(ns_path).lower() == str(username).lower():
                personal.append(p)
            else:
                contributed.append(p)

        return {"personal": personal, "contributed": contributed, "all": unique_projects}

    except Exception as e:
        print(f"Error fetching projects: {e}")
        return {"personal": [], "contributed": [], "all": []}


def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    """
    try:
        # Step 1 & 2: Fetch projects and events
        projects_data = (
            client._get_paginated(
                f"/users/{user_id}/projects",
                params={"simple": "true"},
                per_page=50,
                max_pages=10,
            )
            or []
        )

        events_data = (
            client._get_paginated(
                f"/users/{user_id}/events",
                params={},  # Fetch all actions to catch issues, MRs, comments, etc.
                per_page=100,
                max_pages=5,
            )
            or []
        )

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p["id"] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p["id"])

        event_project_ids = set()
        for e in events_data:
            pid = e.get("project_id")
            if pid and pid not in seen_ids:
                event_project_ids.add(pid)

        # Step 3: Fetch extra project details
        if event_project_ids:
            for pid in event_project_ids:
                try:
                    p_extra = client._get(f"/projects/{pid}", params={"simple": "true"})
                    if p_extra and isinstance(p_extra, dict) and "id" in p_extra:
                        if p_extra["id"] not in seen_ids:
                            unique_projects.append(p_extra)
                            seen_ids.add(p_extra["id"])
                except Exception:
                    pass

        personal = []
        contributed = []

        for p in unique_projects:
            namespace = p.get("namespace", {})
            ns_path = namespace.get("path")
            ns_kind = namespace.get("kind")

            if ns_kind == "user" and str(ns_path).lower() == str(username).lower():
                personal.append(p)
            else:
                contributed.append(p)

        return {"personal": personal, "contributed": contributed, "all": unique_projects}

    except Exception as e:
        print(f"Error fetching projects: {e}")
        return {"personal": [], "contributed": [], "all": []}


def search_projects(client, query):
    """
    Search for projects by name across the GitLab instance.
    """
    return client._get("/projects", params={"search": query, "simple": "true", "per_page": 20})
