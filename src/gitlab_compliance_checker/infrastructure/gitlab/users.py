def get_user_by_username(client, username):
    """
    Fetches a user by username.
    Tries exact match first, then search fallback with local case-insensitive matching.
    """
    print(f"DEBUG: Looking up user '{username}'...")

    # attempt 1: Exact username match
    users = client._get("/users", params={"username": username})

    # attempt 2: Search fallback if no exact match (GitLab 'username' filter can be picky)
    if not users or not isinstance(users, list) or len(users) == 0:
        print(f"DEBUG: Exact match failed, trying search filter for '{username}'...")
        users = client._get("/users", params={"search": username})

    if users and isinstance(users, list) and len(users) > 0:
        # Find the best match locally (case-insensitive)
        target_user = None
        for u in users:
            if str(u.get("username", "")).lower() == str(username).lower():
                target_user = u
                break

        if not target_user:
            return None

        # fetch full user details if ID found
        user_id = target_user.get("id")
        if user_id:
            full_user = client._get(f"/users/{user_id}")
            if full_user:
                return full_user
        return target_user

    return None
