import concurrent.futures


def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    Uses the /contributed_projects endpoint directly for accuracy, then supplements
    with owned projects.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 1. Owned/member projects
            f_owned = executor.submit(
                client._get_paginated,
                f"/users/{user_id}/projects",
                params={"simple": "true"},
                per_page=100,
                max_pages=10,
            )
            # 2. Contributed projects (more accurate than events)
            f_contributed = executor.submit(
                client._get_paginated,
                f"/users/{user_id}/contributed_projects",
                params={"simple": "true"},
                per_page=100,
                max_pages=10,
            )

            owned_data = f_owned.result() or []
            contributed_data = f_contributed.result() or []

        seen_ids = set()
        unique_projects = []

        for p in owned_data + contributed_data:
            if p["id"] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p["id"])

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


def search_projects(client, query):
    """
    Search for projects by name across the GitLab instance.
    """
    return client._get("/projects", params={"search": query, "simple": "true", "per_page": 20})
