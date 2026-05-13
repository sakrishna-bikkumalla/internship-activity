async def get_user_by_username_async(client, username):
    """
    Async fetches a user by username.
    """
    # attempt 1: Exact username match
    users = await client._async_get("/users", params={"username": username})

    # attempt 2: Search fallback
    if not users or not isinstance(users, list) or len(users) == 0:
        users = await client._async_get("/users", params={"search": username})

    if users and isinstance(users, list) and len(users) > 0:
        target_user = None
        for u in users:
            if str(u.get("username", "")).lower() == str(username).lower():
                target_user = u
                break

        if not target_user:
            return None

        user_id = target_user.get("id")
        if user_id:
            full_user = await client._async_get(f"/users/{user_id}")
            if full_user:
                return full_user
        return target_user

    return None


def get_user_by_username(client, username):
    """
    Fetches a user by username.
    Tries exact match first, then search fallback with local case-insensitive matching.
    """
    # attempt 1: Exact username match
    users_data = client._get("/users", params={"username": username})

    # attempt 2: Search fallback
    if not users_data or not isinstance(users_data, list) or len(users_data) == 0:
        users_data = client._get("/users", params={"search": username})

    if users_data and isinstance(users_data, list) and len(users_data) > 0:
        target_user = None
        for u in users_data:
            if str(u.get("username", "")).lower() == str(username).lower():
                target_user = u
                break

        if not target_user:
            return None

        user_id = target_user.get("id")
        if user_id:
            full_user = client._get(f"/users/{user_id}")
            if full_user:
                return full_user
        return target_user

    return None
