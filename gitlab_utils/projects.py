import concurrent.futures

def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    Uses ThreadPoolExecutor to run API calls concurrently.
    """
    try:
        # Step 1 & 2: Fetch projects and events concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 1. projects member
            f_projects = executor.submit(
                client._get_paginated,
                f"/users/{user_id}/projects",
                params={"simple": "true"},
                per_page=50,
                max_pages=10
            )
            # 2. projects from events
            f_events = executor.submit(
                client._get_paginated,
                f"/users/{user_id}/events",
                params={"action": "pushed"},
                per_page=50,
                max_pages=5
            )

            projects_data = f_projects.result() or []
            events_data = f_events.result() or []

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p["id"] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p["id"])

        # Collect event project IDs that aren't already seen
        event_project_ids = set()
        for e in events_data:
            pid = e.get("project_id")
            if pid and pid not in seen_ids:
                event_project_ids.add(pid)

        # Step 3: Fetch extra project details concurrently
        if event_project_ids:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_pid = {
                    executor.submit(client._get, f"/projects/{pid}", params={"simple": "true"}): pid
                    for pid in event_project_ids
                }
                for future in concurrent.futures.as_completed(future_to_pid):
                    p_extra = future.result()
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

            # Personal if namespace matches username and kind is user
            if ns_kind == "user" and str(ns_path).lower() == str(username).lower():
                personal.append(p)
            else:
                contributed.append(p)

        return {"personal": personal, "contributed": contributed, "all": unique_projects}

    except Exception as e:
        print(f"Error fetching projects: {e}")
        return {"personal": [], "contributed": [], "all": []}
