def get_user_groups(client, user_id):
    """
    Fetch all groups the user belongs to.

    The GitLab API endpoint GET /groups?membership=true returns groups for the
    AUTHENTICATED user (token owner), NOT the target user. There is no direct
    per-user group membership endpoint on all GitLab versions.

    Best approach: fetch contributed projects and extract unique namespaces of
    type 'group', which accurately reflects the groups the target user has worked in.
    """
    groups_list = []
    seen_ids = set()

    try:
        # Primary: use /users/{user_id}/contributed_projects to infer group membership
        # This is the most reliable cross-version approach
        contributed = client._get_paginated(
            f"/users/{user_id}/contributed_projects",
            params={"simple": "true"},
            per_page=100,
            max_pages=10,
        )

        for proj in contributed or []:
            ns = proj.get("namespace", {})
            if ns.get("kind") == "group":
                gid = ns.get("id")
                if gid and gid not in seen_ids:
                    seen_ids.add(gid)
                    groups_list.append(
                        {
                            "name": ns.get("name"),
                            "full_path": ns.get("full_path"),
                            "visibility": proj.get("visibility"),
                        }
                    )

        # Secondary: also check owned/member projects for group namespaces
        member_projects = client._get_paginated(
            f"/users/{user_id}/projects",
            params={"simple": "true"},
            per_page=100,
            max_pages=5,
        )
        for proj in member_projects or []:
            ns = proj.get("namespace", {})
            if ns.get("kind") == "group":
                gid = ns.get("id")
                if gid and gid not in seen_ids:
                    seen_ids.add(gid)
                    groups_list.append(
                        {
                            "name": ns.get("name"),
                            "full_path": ns.get("full_path"),
                            "visibility": proj.get("visibility"),
                        }
                    )

    except Exception as e:
        print(f"Error fetching groups: {e}")

    return groups_list
