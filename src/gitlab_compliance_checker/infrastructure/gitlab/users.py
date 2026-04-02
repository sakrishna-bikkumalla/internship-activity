def get_user_by_username(client, username):
    """
    Fetches a user by username.
    Returns the user dict or None if not found.
    """
    users = client._get("/users", params={"username": username})
    if users and isinstance(users, list) and len(users) > 0:
        basic_user = users[0]
        # The basic user lookup might not include email, fetch full user details
        user_id = basic_user.get("id")
        if user_id:
            full_user = client._get(f"/users/{user_id}")
            if full_user:
                return full_user
        return basic_user
    return None
