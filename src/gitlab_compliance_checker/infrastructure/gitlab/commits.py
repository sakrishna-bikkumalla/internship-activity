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
    # Morning: 9:00 AM to 12:29 PM (ends just before afternoon starts)
    # Afternoon: 12:30 PM to 5:00 PM (inclusive)
    morn_start = datetime.strptime("09:00", "%H:%M").time()
    morn_end = datetime.strptime("12:29", "%H:%M").time()
    aft_start = datetime.strptime("12:30", "%H:%M").time()
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

            # Use the most specific search term for the API
            # If email is available, it's usually the best for filtering in GitLab
            search_term = author_email or author_name or username

            if not search_term:
                return p_res

            project_seen_shas = set()
            valid_project_commits = 0

            # Fetch ALL commits from ALL branches without API-side author filter
            # We'll do filtering on the client side to ensure we don't miss commits
            # due to API inconsistencies
            api_params = {"all": "true", "with_stats": "false"}
            if since:
                api_params["since"] = since
            if until:
                api_params["until"] = until

            commits_data = client._get_paginated(
                f"/projects/{pid}/repository/commits",
                params=api_params,
                per_page=100,
                max_pages=500,
            )

            if not commits_data:
                return p_res

            for c in commits_data:
                sha = c.get("id")
                if not sha or sha in project_seen_shas:
                    continue

                # Include merge commits - they count as contributions!
                # No longer filtering out commits with multiple parents

                c_author_name = (c.get("author_name", "") or "").lower()
                c_author_email = (c.get("author_email", "") or "").lower()

                # Strict identity matching - only match if we have strong evidence
                is_match = False
                c_email_local = c_author_email.split("@")[0] if "@" in c_author_email else c_author_email

                # Normalized matching helper (strip spaces and punctuation)
                import re

                def _ns(s):
                    return re.sub(r"[\s_\.\-]", "", (s or "").lower())

                ns_cname = _ns(c_author_name)
                ns_uname = _ns(username)
                ns_aname = _ns(author_name)

                # STRICT: Exact email match (most reliable)
                if author_email and c_author_email and c_author_email == author_email.lower():
                    is_match = True

                # STRICT: Email local part match (user@example.com = username)
                elif author_email and "@" in author_email:
                    email_local = author_email.split("@")[0].lower()
                    if email_local == c_email_local:
                        is_match = True

                # MODERATE: Exact author_name match (full name must match)
                elif author_name and c_author_name and c_author_name == author_name.lower():
                    is_match = True

                # MODERATE: Normalized matching for author name (strip spaces and punctuation)
                elif ns_cname and ns_aname and ns_cname == ns_aname:
                    is_match = True

                # Username matching (only when we have confirmation from email)
                # Match username to email local part (only if user has an email set)
                if not is_match and username and c_email_local:
                    if c_email_local == username.lower():
                        is_match = True

                # Match username to author_name (only as exact normalized match)
                # This handles cases like username="alicedev" matching author_name="alicedev (contractor)"
                if not is_match and username and c_author_name:
                    if ns_cname and ns_uname and ns_cname == ns_uname:
                        is_match = True

                # Allow prefix/suffix match for labels/tags in names (e.g., "alicedev" matches "alicedev (contractor)")
                if not is_match and username and c_author_name and len(ns_uname) >= 3:
                    if ns_cname.startswith(ns_uname) or ns_cname.endswith(ns_uname):
                        is_match = True

                if not is_match:
                    continue

                project_seen_shas.add(sha)
                valid_project_commits += 1

                # Store for processing
                p_res["commits"].append(
                    {
                        "sha": sha,
                        "pname": pname,
                        "title": c.get("title"),
                        "created_at": c.get("created_at"),
                        "author_name": c.get("author_name"),
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
                    if t_obj >= morn_start and t_obj <= morn_end:
                        slot = "Morning"
                        stats["morning_commits"] += 1
                    elif t_obj >= aft_start and t_obj <= aft_end:
                        slot = "Afternoon"
                        stats["afternoon_commits"] += 1

                except Exception:
                    date_str = created_at_str.split("T")[0] if created_at_str else "N/A"
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
