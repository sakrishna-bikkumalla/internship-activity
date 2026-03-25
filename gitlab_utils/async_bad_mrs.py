"""
async_bad_mrs.py
~~~~~~~~~~~~~~~~
RELIABILITY-FIRST BAD MRs engine.
Rewritten with full native asyncio/aiohttp concurrency for maximum speed.
- Parallel User ID lookups.
- Capped scan depth (20 MRs per user) for guaranteed speed.
- Smart evaluation: concurrent sub-resource fetching.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import aiohttp

# Allowed imports
from gitlab_utils.description_quality import analyze_description

# BATCH_USERNAMES etc constant moved down or kept...

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BATCH_USERNAMES: list[str] = [
    "prav2702",
    "saikrishna_b",
    "MohanaSriBhavitha",
    "praneethashish",
    "kanukuntagreeshma2004",
    "vandana1735",
    "vandana_rajuldev",
    "Mukthanand21",
    "Shanmukh16",
    "Sathwikareddy_Damanagari",
    "Sahasraa",
    "laxmanreddypatlolla",
    "Abhilash653",
    "LagichettyKushal",
    "Lakshy",
    "Suma2304",
    "koushik_18",
    "kumari123",
    "Habeebunissa",
    "Bhaskar_Battula",
    "Pranav_rs",
    "vai5h",
    "Saiharshavardhan",
    "Rushika_1105",
    "swarna_4539",
    "satish05",
    "aravindswamy",
    "pavaninagireddi",
    "jeevana_31",
    "saiteja3005",
    "SandhyaRani_111",
    "klaxmi1908",
    "Kaveri_Mamidi",
    "Pavani_Pothuganti",
]

_ZERO_ROW = {
    "Username": "",
    "Closed MRs": 0,
    "No Desc": 0,
    "Improper Desc": 0,
    "No Issues": 0,
    "No Time Spent": 0,
    "No Unit Tests": 0,
    "Failed Pipeline": 0,
    "No Semantic Commits": 0,
    "No Internal Review": 0,
    "Merge > 1 Week": 0,
    "Merge > 2 Days": 0,
}


async def fetch_json(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore, **kwargs):
    retries = 3
    for attempt in range(retries):
        async with sem:
            try:
                # SSL False for enterprise compatibility if needed
                async with session.get(url, ssl=False, **kwargs) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_limit = int(retry_after)
                                if wait_limit > 60:
                                    raise Exception(
                                        f"GitLab API Rate Limit Exceeded. Please try again after {wait_limit} seconds."
                                    )
                            except ValueError:
                                pass

                        if attempt < retries - 1:
                            await asyncio.sleep(3**attempt)  # aggressive backoff
                            continue
                        else:
                            raise Exception(
                                "GitLab API Rate Limit Exceeded (429 Too Many Requests). Max retries reached."
                            )
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 204:
                        return None
                    else:
                        return None
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Error fetching {url}: {e}")
                    raise e
                await asyncio.sleep(1)
    return None


async def _evaluate_single_mr(
    session: aiohttp.ClientSession, sem: asyncio.Semaphore, base_url: str, headers: dict, mr: dict
) -> tuple[str, dict]:
    uname = mr.get("_username", "unknown")
    pid, iid = mr["project_id"], mr["iid"]
    flags = {
        "is_terminal": mr.get("state") in ("merged", "closed"),
        "is_merged": mr.get("state") == "merged",
        "is_closed_rejected": mr.get("state") == "closed",
        "no_desc": False,
        "improper_desc": False,
        "no_issues": False,
        "no_time": False,
        "no_unit_tests": False,
        "failed_pipe": False,
        "no_semantic_commits": False,
        "no_internal_review": True,
        "merge_gt_2_days": False,
        "merge_gt_1_week": False,
    }

    try:
        desc = mr.get("description") or ""
        if not str(desc).strip():
            flags["no_desc"] = True
        try:
            if analyze_description(desc)["quality_label"] != "High":
                flags["improper_desc"] = True
        except Exception:
            pass

        api_base = f"{base_url}/api/v4"

        # 1. Pipeline Check (Fetch full MR conditionally if pipeline is missing)
        pipeline = mr.get("pipeline")
        if pipeline and isinstance(pipeline, dict):
            if pipeline.get("status") == "failed":
                flags["failed_pipe"] = True
        elif flags["is_closed_rejected"]:
            # Fallback API call to get pipelines accurately for rejected MRs
            try:
                pl = await fetch_json(
                    session, f"{api_base}/projects/{pid}/merge_requests/{iid}/pipelines", sem, headers=headers
                )
                if pl and isinstance(pl, list) and len(pl) > 0:
                    if pl[0].get("status") == "failed":
                        flags["failed_pipe"] = True
            except Exception as pe:
                if "Rate Limit" in str(pe):
                    raise pe

        # 2. Time Spent Check (Use embedded time_stats from list endpoint)
        ts = mr.get("time_stats", {})
        if isinstance(ts, dict) and ts.get("total_time_spent", 0) == 0:
            flags["no_time"] = True

        # 4. Semantic Commits Check (Check all commits in the MR)
        try:
            m_commits = await fetch_json(
                session, f"{api_base}/projects/{pid}/merge_requests/{iid}/commits", sem, headers=headers
            )
            if m_commits and isinstance(m_commits, list):
                has_any_semantic = False
                for c in m_commits:
                    c_msg = str(c.get("message", "")).lower()
                    if re.match(r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?:", c_msg):
                        has_any_semantic = True
                        break
                flags["no_semantic_commits"] = not has_any_semantic
            else:
                # Fallback to title if no commits found (e.g. error)
                title = str(mr.get("title") or "")
                title_lower = title.lower()
                if not re.match(
                    r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?:", title_lower
                ):
                    flags["no_semantic_commits"] = True
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            flags["no_semantic_commits"] = True

        # 5. Internal Review (Verify human notes exist from others)
        try:
            m_notes = await fetch_json(
                session, f"{api_base}/projects/{pid}/merge_requests/{iid}/notes", sem, headers=headers
            )
            has_external_human_review = False
            mr_author_id = mr.get("author", {}).get("id")

            if m_notes and isinstance(m_notes, list):
                for n in m_notes:
                    # Must be non-system AND not from the MR author
                    if not n.get("system") and n.get("author", {}).get("id") != mr_author_id:
                        has_external_human_review = True
                        break

            # Count upvotes as review too (usually others upvote)
            if not has_external_human_review and mr.get("upvotes", 0) > 0:
                has_external_human_review = True

            flags["no_internal_review"] = not has_external_human_review
        except Exception as e:
            if "Rate Limit" in str(e):
                raise e
            flags["no_internal_review"] = True

        # 6. Issues check (Permissive Regex first, minimizing API calls)
        title = str(mr.get("title") or "")
        desc = str(mr.get("description") or "")
        content_to_check = f"{title} {desc}"
        if re.search(r"#\d+|issue\s*#?\d+|\[\d+\]", content_to_check, re.IGNORECASE):
            flags["no_issues"] = False
        else:
            # Fallback API call ONLY if regex fails
            iss = await fetch_json(
                session, f"{api_base}/projects/{pid}/merge_requests/{iid}/issues", sem, headers=headers
            )
            if not iss:
                flags["no_issues"] = True

        # 7. Unit Tests check
        if "test" in title_lower or "spec" in title_lower:
            flags["no_unit_tests"] = False
        else:
            # Fallback API call ONLY if title doesn't state it
            chg = await fetch_json(
                session, f"{api_base}/projects/{pid}/merge_requests/{iid}/changes", sem, headers=headers
            )
            h_tests = False
            if chg and isinstance(chg, dict):
                for c in chg.get("changes", []):
                    new_p = str(c.get("new_path", "")).lower()
                    old_p = str(c.get("old_path", "")).lower()
                    if "test" in new_p or "spec" in new_p or "test" in old_p or "spec" in old_p:
                        h_tests = True
                        break
            if not h_tests:
                flags["no_unit_tests"] = True

        # Time tracking
        created_s = mr.get("created_at")
        merged_s = mr.get("merged_at")
        if created_s:
            try:
                created_dt = datetime.strptime(created_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                if merged_s:
                    end_dt = datetime.strptime(merged_s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                elif mr.get("state") == "closed" and mr.get("closed_at"):
                    end_dt = datetime.strptime(mr.get("closed_at")[:19], "%Y-%m-%dT%H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                else:
                    end_dt = datetime.now(timezone.utc)

                days_diff = (end_dt - created_dt).total_seconds() / 86400
                if days_diff > 2:
                    flags["merge_gt_2_days"] = True
                if days_diff > 7:
                    flags["merge_gt_1_week"] = True
            except Exception:
                pass

    except Exception as e:
        if "Rate Limit Exceeded" in str(e):
            raise e
        print(f"Error evaluating MR {iid} for {uname}: {e}")

    return uname, flags


async def _fetch_user_mrs(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    base_url: str,
    headers: dict,
    uname: str,
    project_id: str | None = None,
    group_id: str | None = None,
) -> list[dict]:
    api_base = f"{base_url}/api/v4"
    u_data = await fetch_json(session, f"{api_base}/users", sem, headers=headers, params={"username": uname})
    if not u_data:
        return []

    # Exact match check to avoid similar usernames (e.g. kumari123 matching kumari1234)
    target_user = None
    if isinstance(u_data, list):
        for u in u_data:
            if str(u.get("username", "")).lower() == str(uname).lower():
                target_user = u
                break

    if not target_user:
        return []

    uid = target_user["id"]
    # Accuracy over Speed: Fetch 100 MRs instead of 20
    params = {"author_id": str(uid), "scope": "all", "per_page": "100", "page": "1"}
    if project_id:
        params["project_id"] = project_id
    if group_id:
        params["group_id"] = group_id

    mrs = await fetch_json(session, f"{api_base}/merge_requests", sem, headers=headers, params=params)

    if not mrs:
        return []

    for mr in mrs:
        mr["_username"] = uname
    return mrs


async def _run_batch(
    client, usernames: list[str], project_id: str | None = None, group_id: str | None = None
) -> list[dict]:
    result_map = {u: {**_ZERO_ROW, "Username": u} for u in usernames}

    base_url = client.base_url.rstrip("/")
    headers = client.headers

    # 25 concurrent connections is highly optimal and stays below typical GitLab rate limits
    sem = asyncio.Semaphore(25)
    connector = aiohttp.TCPConnector(limit=25, ssl=False)

    print(f"DEBUG: Starting async batch fetch for {len(usernames)} users...")

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Fetch all user MRs concurrently
        user_tasks = [_fetch_user_mrs(session, sem, base_url, headers, u, project_id, group_id) for u in usernames]
        all_users_mrs = await asyncio.gather(*user_tasks)

        all_mr_tasks = []
        for mr_list in all_users_mrs:
            all_mr_tasks.extend(mr_list)

        print(f"DEBUG: Found {len(all_mr_tasks)} MRs across all users.")

        # 2. Evaluate all MRs concurrently
        eval_tasks = [_evaluate_single_mr(session, sem, base_url, headers, mr) for mr in all_mr_tasks]
        eval_results = await asyncio.gather(*eval_tasks)

        for uname, f in eval_results:
            if uname in result_map:
                row = result_map[uname]

                # AGGREGATION: Metrics for Closed MRs only
                if f.get("is_closed_rejected"):
                    row["Closed MRs"] += 1

                    # 1. Pipeline Audit: Count for Closed MRs only
                    if f.get("failed_pipe"):
                        row["Failed Pipeline"] += 1

                    # 2. Compliance Audit: Count ONLY for Closed MRs
                    if f.get("no_desc"):
                        row["No Desc"] += 1
                    if f.get("improper_desc"):
                        row["Improper Desc"] += 1
                    if f.get("no_issues"):
                        row["No Issues"] += 1
                    if f.get("no_time"):
                        row["No Time Spent"] += 1
                    if f.get("no_unit_tests"):
                        row["No Unit Tests"] += 1

                    # 3. New metrics - count ONLY for Closed MRs to maintain mathematical consistency
                    if f.get("no_semantic_commits"):
                        row["No Semantic Commits"] += 1
                    if f.get("no_internal_review"):
                        row["No Internal Review"] += 1
                    if f.get("merge_gt_1_week"):
                        row["Merge > 1 Week"] += 1
                    if f.get("merge_gt_2_days"):
                        row["Merge > 2 Days"] += 1

    return sorted(result_map.values(), key=lambda r: r["Username"])


def fetch_all_bad_mrs(
    client, usernames: list[str], project_id: str | None = None, group_id: str | None = None
) -> list[dict]:
    import nest_asyncio

    nest_asyncio.apply()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_run_batch(client, usernames, project_id, group_id))


def _check_user_compliance(client, username: str) -> dict:
    # Small wrapper for test suite compatibility
    res = fetch_all_bad_mrs(client, [username])
    return res[0] if res else {**_ZERO_ROW, "Username": username}
