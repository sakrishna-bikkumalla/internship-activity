def get_user_mrs(client, user_id):
    """
    Fetch Merge Requests:
    - Authored MRs (GET /merge_requests?author_id=:id)
    - Assigned MRs (GET /merge_requests?assignee_id=:id)

    Returns:
      - mrs_list: List of MR dicts
      - stats: Dict {total, merged, closed, opened, pending}
    """
    mrs_list = []
    seen_ids = set()

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0, # "opened" acts as Pending often
        "pending": 0 # Explicit pending check if needed (usually 'opened')
    }

    # helper to fetch and process
    def fetch_and_add(params, role_label):
        try:
            items = client._get_paginated("/merge_requests", params=params, per_page=50, max_pages=10)
            for item in items:
                if item['id'] not in seen_ids:
                    state = item.get("state") # opened, closed, merged, locked

                    mrs_list.append({
                        "title": item.get("title"),
                        "project_id": item.get("project_id"),
                        "web_url": item.get("web_url"),
                        "state": state,
                        "created_at": item.get("created_at"),
                        "role": role_label
                    })
                    seen_ids.add(item['id'])

                    # Update Stats
                    stats["total"] += 1
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_and_add({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, "Assigned")

    return mrs_list, stats
