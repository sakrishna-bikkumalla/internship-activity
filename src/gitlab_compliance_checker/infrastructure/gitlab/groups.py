import asyncio


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


async def get_group_members_async(client, group_path: str, limit: int | None = None):
    """
    Async fetch members of a group given its URL-encoded path or ID.
    Uses /groups/{id}/members/all to get all inherited members as well.
    """
    members_list = []
    try:
        encoded_path = group_path.replace("/", "%2F")
        members = await client._async_get_paginated(
            f"/groups/{encoded_path}/members/all",
            params={},
            per_page=100,
            max_pages=100 if limit is None else (limit // 100) + 1,
        )

        async def _fetch_member_email(m):
            uname = m.get("username")
            uid = m.get("id")
            if not uname and not uid:
                return ""

            email = ""
            try:
                # Attempt 1: Search by username (sometimes returns email in list if permissions allow)
                if uname:
                    users_data = await client._async_get("/users", params={"username": uname})
                    if users_data and isinstance(users_data, list):
                        for u in users_data:
                            if str(u.get("username", "")).lower() == str(uname).lower():
                                email = u.get("email") or u.get("public_email") or u.get("notification_email") or ""
                                if email:
                                    break

                # Attempt 2: Fetch full profile by ID (standard logic from users.py)
                if not email and uid:
                    full_user = await client._async_get(f"/users/{uid}")
                    if full_user and isinstance(full_user, dict):
                        email = (
                            full_user.get("email")
                            or full_user.get("public_email")
                            or full_user.get("notification_email")
                            or ""
                        )
            except Exception:
                pass
            return email

        # Fetch emails in parallel
        members_to_process = members[:limit] if limit else members
        email_tasks = [_fetch_member_email(m) for m in members_to_process]
        emails = await asyncio.gather(*email_tasks)

        for i, m in enumerate(members_to_process):
            members_list.append(
                {
                    "id": m.get("id"),
                    "username": m.get("username"),
                    "name": m.get("name"),
                    "email": emails[i],
                    "avatar_url": m.get("avatar_url"),
                    "web_url": m.get("web_url"),
                }
            )
    except Exception as e:
        print(f"Error fetching group members: {e}")

    return members_list


def get_group_members(client, group_path: str, limit: int | None = None):
    """
    Fetch members of a group given its URL-encoded path or ID.
    Uses /groups/{id}/members/all to get all inherited members as well.
    """
    members_list = []
    try:
        encoded_path = group_path.replace("/", "%2F")
        members = client._get_paginated(
            f"/groups/{encoded_path}/members/all",
            params={},
            per_page=100,
            max_pages=100 if limit is None else (limit // 100) + 1,
        )

        for m in members[:limit] if limit else members:
            email = ""
            uname = m.get("username")
            uid = m.get("id")

            try:
                # Attempt 1: Search by username
                if uname:
                    users_data = client._get("/users", params={"username": uname})
                    if users_data and isinstance(users_data, list):
                        for u in users_data:
                            if str(u.get("username", "")).lower() == str(uname).lower():
                                email = u.get("email") or u.get("public_email") or u.get("notification_email") or ""
                                if email:
                                    break

                # Attempt 2: Fetch full profile by ID
                if not email and uid:
                    full_user = client._get(f"/users/{uid}")
                    if full_user and isinstance(full_user, dict):
                        email = (
                            full_user.get("email")
                            or full_user.get("public_email")
                            or full_user.get("notification_email")
                            or ""
                        )
            except Exception:
                pass

            members_list.append(
                {
                    "id": m.get("id"),
                    "username": m.get("username"),
                    "name": m.get("name"),
                    "email": email,
                    "avatar_url": m.get("avatar_url"),
                    "web_url": m.get("web_url"),
                }
            )
    except Exception as e:
        print(f"Error fetching group members: {e}")

    return members_list
