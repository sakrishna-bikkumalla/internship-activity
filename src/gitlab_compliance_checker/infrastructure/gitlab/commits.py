import asyncio
import concurrent.futures
import re
import threading
from datetime import datetime, timedelta, timezone

import dateutil.parser


async def get_user_commits_async(client, user, projects, since=None, until=None):
    """
    Async fetches commits for a user across given projects.
    """
    all_commits = []
    project_commit_counts = {}
    seen_shas = set()

    author_name = user.get("name")
    author_email = user.get("email")
    username = user.get("username")
    ist = timezone(timedelta(hours=5, minutes=30))

    morn_start = datetime.strptime("09:00", "%H:%M").time()
    morn_end = datetime.strptime("12:29", "%H:%M").time()
    aft_start = datetime.strptime("12:30", "%H:%M").time()
    aft_end = datetime.strptime("17:00", "%H:%M").time()

    stats = {
        "total": 0,
        "morning_commits": 0,
        "afternoon_commits": 0,
    }

    async def _fetch_project_commits(project):
        pid = project.get("id")
        pname = project.get("name_with_namespace")
        search_term = author_email or author_name or username
        if not search_term:
            return {"pid": pid, "commits": [], "count": 0, "error": None}

        try:
            api_params = {"all": "true", "with_stats": "false"}
            if since:
                api_params["since"] = since
            if until:
                api_params["until"] = until

            commits_data = await client._async_get_paginated(
                f"/projects/{pid}/repository/commits",
                params=api_params,
                per_page=100,
                max_pages=500,
            )

            p_commits = []
            v_count = 0
            p_seen = set()

            def _ns(s):
                return re.sub(r"[\s_\.\-]", "", (s or "").lower())

            ns_uname = _ns(username)
            ns_aname = _ns(author_name)

            for c in commits_data or []:
                sha = c.get("id")
                if not sha or sha in p_seen:
                    continue

                c_author_name = (c.get("author_name", "") or "").lower()
                c_author_email = (c.get("author_email", "") or "").lower()
                c_email_local = c_author_email.split("@")[0] if "@" in c_author_email else c_author_email
                ns_cname = _ns(c_author_name)

                is_match = False
                if author_email and c_author_email == author_email.lower():
                    is_match = True
                elif username and c_email_local == username.lower():
                    is_match = True
                elif author_email and "@" in author_email and author_email.split("@")[0].lower() == c_email_local:
                    is_match = True
                elif ns_cname and (ns_uname and ns_cname == ns_uname):
                    is_match = True
                elif ns_cname and (ns_aname and ns_cname == ns_aname):
                    is_match = True

                if is_match:
                    p_seen.add(sha)
                    v_count += 1
                    p_commits.append(
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
            return {"pid": pid, "commits": p_commits, "count": v_count, "error": None}
        except Exception as e:
            return {"pid": pid, "commits": [], "count": 0, "error": str(e)}

    # Fetch all projects concurrently
    results = await asyncio.gather(*[_fetch_project_commits(p) for p in projects])

    for res in results:
        pid = res["pid"]
        project_commit_counts[pid] = res["count"]
        if res["error"]:
            continue

        for c in res["commits"]:
            sha = c["sha"]
            if sha in seen_shas:
                continue
            seen_shas.add(sha)
            stats["total"] += 1

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


def get_user_commits(client, user, projects, since=None, until=None):
    """
    Fetches all commits from the given list of projects and matches them to the user.
    Uses ThreadPoolExecutor to run API calls in parallel.
    """
    all_commits = []
    # Project ID -> count mapping for tests
    project_counts = {}
    commit_slots = {"Morning": 0, "Afternoon": 0, "Other": 0}
    seen_shas = set()
    shas_lock = threading.Lock()

    username = str(user.get("username", "")).lower()
    display_name = str(user.get("name", "")).lower()
    user_email = str(user.get("email", "")).lower()

    date_params = {}
    if since:
        date_params["since"] = since
    if until:
        date_params["until"] = until

    def process_project(project):
        p_commits = []
        pid = project.get("id")
        try:
            items = client._get_paginated(
                f"/projects/{pid}/repository/commits",
                params={**date_params, "all": "true"},
                per_page=100,
                max_pages=50,
            )
            count = 0
            for item in items:
                author_name = str(item.get("author_name", "")).lower()
                author_email = str(item.get("author_email", "")).lower()
                sha = item.get("id")

                match = False
                if author_email == user_email and user_email:
                    match = True
                elif author_name == display_name and display_name:
                    match = True
                elif username in author_email and username:
                    match = True
                elif username == author_name and username:
                    match = True

                if match:
                    with shas_lock:
                        if sha not in seen_shas:
                            seen_shas.add(sha)
                            should_add = True
                        else:
                            should_add = False

                    if should_add:
                        count += 1
                        timestamp_str = item.get("created_at")
                        try:
                            dt = dateutil.parser.parse(timestamp_str)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            ist_dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))

                            hour = ist_dt.hour
                            slot = "Other"
                            if 9 <= hour < 13:
                                slot = "Morning"
                            elif 14 <= hour < 18:
                                slot = "Afternoon"
                            time_str = ist_dt.strftime("%H:%M:%S")
                        except Exception:
                            slot = "N/A"
                            time_str = "N/A"
                            ist_dt = None

                        p_commits.append(
                            {
                                "project_name": project.get("name") or project.get("name_with_namespace"),
                                "message": item.get("message"),
                                "date": ist_dt.strftime("%Y-%m-%d") if ist_dt else "N/A",
                                "time": time_str,
                                "slot": slot,
                                "sha": sha,
                                "author_name": item.get("author_name"),
                                "web_url": (project.get("web_url") or "") + f"/-/commit/{sha}"
                                if project.get("web_url") or project.get("id")
                                else "",
                            }
                        )
            return pid, p_commits, count
        except Exception:
            return pid, [], 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_proj = {executor.submit(process_project, p): p for p in projects}
        for future in concurrent.futures.as_completed(future_to_proj):
            pid, res, p_count = future.result()
            all_commits.extend(res)
            if pid:
                project_counts[pid] = p_count

    for c in all_commits:
        if c["slot"] in commit_slots:
            commit_slots[c["slot"]] += 1

    total = len(all_commits)
    commit_stats = {
        "total": total,
        "morning_commits": commit_slots["Morning"],
        "afternoon_commits": commit_slots["Afternoon"],
        "morning_pct": round((commit_slots["Morning"] / total * 100), 1) if total > 0 else 0,
        "afternoon_pct": round((commit_slots["Afternoon"] / total * 100), 1) if total > 0 else 0,
    }

    return all_commits, project_counts, commit_stats
