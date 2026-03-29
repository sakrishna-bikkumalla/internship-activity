import concurrent.futures
from datetime import datetime, timedelta, timezone

import dateutil.parser


def get_user_commits(client, user, projects, since=None, until=None):
    """
    Fetches commits for a user across given projects concurrently.
    Returns:
      - all_commits: List of unique commit dicts
      - project_commit_counts: Dict {project_id: count}
      - stats: Dict {morning_commits, afternoon_commits, total}
    """
    all_commits = []
    project_commit_counts = {}
    seen_shas = set()

    # Use name and email for stricter filtering
    author_name = user.get("name")
    author_email = user.get("email")
    username = user.get("username")

    # Define IST timezone (+5:30)
    ist = timezone(timedelta(hours=5, minutes=30))

    # Define slot boundary times for comparison
    morn_start = datetime.strptime("09:30", "%H:%M").time()
    morn_end = datetime.strptime("12:30", "%H:%M").time()
    aft_start = datetime.strptime("14:00", "%H:%M").time()
    aft_end = datetime.strptime("17:00", "%H:%M").time()

    stats = {
        "total": 0,
        "morning_commits": 0,
        "afternoon_commits": 0,
    }

    def _fetch_project_commits(project):
        """Worker to fetch commits for a single project."""
        p_res = {"pid": project.get("id"), "commits": [], "count": 0, "error": None}
        try:
            pid = project.get("id")
            pname = project.get("name_with_namespace")

            author_search_terms = []
            if author_name:
                author_search_terms.append(author_name)
            if username and username not in author_search_terms:
                author_search_terms.append(username)
            if not author_search_terms and author_email:
                author_search_terms.append(author_email)

            project_seen_shas = set()
            valid_project_commits = 0

            for search_term in author_search_terms:
                api_params = {"author": search_term, "all": True}
                if since:
                    api_params["since"] = since
                if until:
                    api_params["until"] = until

                commits_data = client._get_paginated(
                    f"/projects/{pid}/repository/commits",
                    params=api_params,
                    per_page=100,
                    max_pages=20,
                )

                if not commits_data:
                    continue

                for c in commits_data:
                    sha = c.get("id")
                    if not sha or sha in project_seen_shas:
                        continue

                    c_author_name = c.get("author_name", "") or ""
                    c_author_email = c.get("author_email", "") or ""

                    # Trust the GitLab API's author filter primarily, but validate
                    # to avoid false positives when the API does partial matching.
                    c_author_name_l = c_author_name.lower()
                    c_author_email_l = c_author_email.lower()

                    is_match = False
                    if author_name and c_author_name_l == author_name.lower():
                        is_match = True
                    elif author_email and c_author_email_l == author_email.lower():
                        is_match = True
                    elif username and (
                        username.lower() in c_author_name_l or username.lower() in c_author_email_l
                    ):
                        is_match = True
                    elif not (author_name or author_email or username):
                        is_match = True  # No filter criteria — accept all

                    if not is_match:
                        continue

                    project_seen_shas.add(sha)
                    valid_project_commits += 1

                    # Store for processing (time parsing is done in main thread to avoid dict sync issues)
                    p_res["commits"].append(
                        {
                            "sha": sha,
                            "pname": pname,
                            "title": c.get("title"),
                            "created_at": c.get("created_at"),
                            "author_name": c_author_name,
                            "short_id": c.get("short_id"),
                            "web_url": c.get("web_url"),
                        }
                    )

            p_res["count"] = valid_project_commits

        except Exception as e:
            p_res["error"] = str(e)

        return p_res

    # Run per-project fetching in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_project = {executor.submit(_fetch_project_commits, p): p for p in projects}
        for future in concurrent.futures.as_completed(future_to_project):
            res = future.result()
            pid = res["pid"]
            project_commit_counts[pid] = res["count"]

            if res["error"]:
                print(f"Warning: Could not fetch commits for project {pid}: {res['error']}")
                continue

            for c in res["commits"]:
                sha = c["sha"]
                if sha in seen_shas:
                    continue
                seen_shas.add(sha)
                stats["total"] += 1

                # Parse and process time in main thread
                created_at_str = c["created_at"]
                try:
                    dt = dateutil.parser.isoparse(created_at_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt_ist = dt.astimezone(ist)

                    date_str = dt_ist.strftime("%Y-%m-%d")
                    time_str = dt_ist.strftime("%I:%M %p")
                    t_obj = dt_ist.time()

                    slot = "Other"
                    if t_obj >= morn_start and t_obj < morn_end:
                        slot = "Morning"
                        stats["morning_commits"] += 1
                    elif t_obj >= aft_start and t_obj <= aft_end:
                        slot = "Afternoon"
                        stats["afternoon_commits"] += 1

                except Exception:
                    date_str = created_at_str
                    time_str = "N/A"
                    slot = "N/A"

                all_commits.append(
                    {
                        "project_name": c["pname"],
                        "message": c["title"],
                        "date": date_str,
                        "time": time_str,
                        "slot": slot,
                        "author_name": c["author_name"],
                        "short_id": c["short_id"],
                        "web_url": c["web_url"],
                    }
                )

    return all_commits, project_commit_counts, stats
