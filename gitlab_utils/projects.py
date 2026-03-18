def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    """
    try:
        # Fetch projects where user is a member
        # User request: "GET /projects?membership=true"
        # This catches projects the user has access to (member or owner).

        # We need paginated results for potentially many projects.
        # 1. Fetch direct projects
        projects_data = client._get_paginated(
            f"/users/{user_id}/projects", params={"simple": "true"}, per_page=50, max_pages=10
        )

        # 2. Fetch projects from Events (Contribution discovery)
        # This catches projects user pushed to but might not be returned by /projects
        events_data = client._get_paginated(
            f"/users/{user_id}/events", params={"action": "pushed"}, per_page=50, max_pages=5
        )

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p["id"] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p["id"])

        # Fetch extra projects found in events
        event_project_ids = set()
        for e in events_data:
            pid = e.get("project_id")
            if pid and pid not in seen_ids:
                event_project_ids.add(pid)

        for pid in event_project_ids:
            # Fetch the project object for this ID
            p_extra = client._get(f"/projects/{pid}", params={"simple": "true"})
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
