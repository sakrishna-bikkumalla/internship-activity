async def get_user_groups_async(client, user_id):
    """
    Async fetch all groups the user belongs to.
    """
    groups_list = []
    try:
        groups = await client._async_get_paginated(
            "/groups",
            params={"membership": "true", "min_access_level": 10},
            per_page=50,
            max_pages=10,
        )

        seen_ids = set()
        for g in groups:
            if g["id"] in seen_ids:
                continue
            seen_ids.add(g["id"])

            groups_list.append(
                {
                    "name": g.get("name"),
                    "full_path": g.get("full_path"),
                    "visibility": g.get("visibility"),
                }
            )
    except Exception as e:
        print(f"Error fetching groups: {e}")

    return groups_list


def get_user_groups(client, user_id):
    """
    Fetch all groups the user belongs to.
    """
    groups_list = []
    try:
        groups_data = client._get_paginated(
            "/groups",
            params={"membership": "true", "min_access_level": 10},
            per_page=50,
            max_pages=10,
        )

        seen_ids = set()
        for g in groups_data:
            if g["id"] in seen_ids:
                continue
            seen_ids.add(g["id"])

            groups_list.append(
                {
                    "name": g.get("name"),
                    "full_path": g.get("full_path"),
                    "visibility": g.get("visibility"),
                }
            )
    except Exception as e:
        print(f"Error fetching groups: {e}")

    return groups_list
