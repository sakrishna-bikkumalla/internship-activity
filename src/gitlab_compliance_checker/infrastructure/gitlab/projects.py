import asyncio
from urllib.parse import urlparse


def extract_path_from_url(input_str: str) -> str:
    """Extract project path from GitLab URL or return input as is."""
    try:
        path = urlparse(input_str).path.strip("/")
        if path.endswith(".git"):
            return path[:-4]
        return path
    except Exception:
        return input_str.strip()


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
    Fetches all projects for a user asynchronously.
    """
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
            params={"action": "pushed"},
            per_page=50,
            max_pages=20,
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
                params={"action": "pushed"},
                per_page=50,
                max_pages=20,
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
