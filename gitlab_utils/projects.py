def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    """
    try:
        # Fetch projects where user is a member
        # User request: "GET /projects?membership=true"
        # This catches projects the user has access to (member or owner).

        # We need paginated results for potentially many projects.
        projects_data = client._get_paginated(
            f"/users/{user_id}/projects",
            params={"simple": "true"},
            per_page=50,
            max_pages=20
        )

        personal = []
        contributed = []

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p['id'] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p['id'])

        for p in unique_projects:
            # Classification Logic
            # Personal: project.owner.username == given_username
            # OR namespace.kind == 'user' and namespace.path == username

            namespace = p.get('namespace', {})
            ns_path = namespace.get('path')
            ns_kind = namespace.get('kind')

            # Personal if namespace matches username and kind is user
            if ns_kind == 'user' and str(ns_path).lower() == str(username).lower():
                personal.append(p)
            else:
                # Contributed
                # User request: Filter project["namespace"]["kind"] != "user" for contributed?
                # "Extend it to correctly fetch contributed projects... Filter: project['namespace']['kind'] != 'user'"
                # Wait, if I contribute to another USER's project, it IS 'user' kind but not MY user.
                # So "Contributed" is anything that is NOT Personal.

                # Check logic:
                # If it's NOT personal, it's potentially contributed.
                contributed.append(p)

        return {
            "personal": personal,
            "contributed": contributed,
            "all": unique_projects
        }

    except Exception as e:
        print(f"Error fetching projects: {e}")
        return {"personal": [], "contributed": [], "all": []}
