def get_user_by_username(client, username):
    """
    Fetches a user by username.
    Returns the user dict or None if not found.
    """
    users = client._get("/users", params={"username": username})
    if users and isinstance(users, list) and len(users) > 0:
        return users[0]  # Exact match usually returns one
    return None
