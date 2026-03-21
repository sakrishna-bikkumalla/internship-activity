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
import aiohttp
import re
import nest_asyncio

from gitlab_utils.description_quality import analyze_description

# Allow asyncio loops to be nested, making it Streamlit-safe
nest_asyncio.apply()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BATCH_USERNAMES: list[str] = [
    "prav2702", "saikrishna_b", "MohanaSriBhavitha", "praneethashish",
    "kanukuntagreeshma2004", "vandana1735", "vandana_rajuldev",
    "Mukthanand21", "Shanmukh16", "Sathwikareddy_Damanagari", "Sahasraa",
    "laxmanreddypatlolla", "Abhilash653", "LagichettyKushal", "Lakshy",
    "Suma2304", "koushik_18", "kumari123", "Habeebunissa", "Bhaskar_Battula",
    "Pranav_rs", "vai5h", "Saiharshavardhan", "Rushika_1105", "swarna_4539",
    "satish05", "aravindswamy", "pavaninagireddi", "jeevana_31", "saiteja3005",
    "SandhyaRani_111", "klaxmi1908", "Kaveri_Mamidi", "Pavani_Pothuganti",
]

_ZERO_ROW = {
    "Username": "", "Closed MRs": 0, "No Description": 0,
    "Improper Description": 0, "No Issues Linked": 0, "No Time Spent": 0,
    "No Unit Tests": 0, "Failed Pipeline": 0,
}

async def fetch_json(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore, **kwargs):
    retries = 3
    for attempt in range(retries):
        async with sem:
            try:
                # SSL False for enterprise compatibility if needed
                async with session.get(url, ssl=False, **kwargs) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(3 ** attempt) # aggressive backoff
                        continue
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 204:
                        return None
                    else:
                        return None
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Error fetching {url}: {e}")
                    return None
                await asyncio.sleep(1)
    return None

async def _evaluate_single_mr(session: aiohttp.ClientSession, sem: asyncio.Semaphore, base_url: str, headers: dict, mr: dict) -> tuple[str, dict]:
    uname = mr.get("_username", "unknown")
    pid, iid = mr["project_id"], mr["iid"]
    flags = {
        "is_closed": mr.get("state") in ("merged", "closed"),
        "no_desc": False, "improper_desc": False, "no_issues": False,
        "no_time": False, "no_unit_tests": False, "failed_pipe": False
    }

    try:
        desc = mr.get("description") or ""
        if not str(desc).strip(): flags["no_desc"] = True
        try:
            if analyze_description(desc)["quality_label"] != "High":
                flags["improper_desc"] = True
        except: pass

        api_base = f"{base_url}/api/v4"

        # Parallel fetch for sub-resources
        full_mr_task = fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}", sem, headers=headers)
        ts_task = fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}/time_stats", sem, headers=headers)
        iss_task = fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}/issues", sem, headers=headers)
        chg_task = fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}/changes", sem, headers=headers)

        full_mr, ts, iss, chg = await asyncio.gather(full_mr_task, ts_task, iss_task, chg_task)

        if full_mr:
            full_desc = full_mr.get("description") or ""
            if not str(full_desc).strip(): flags["no_desc"] = True
            hp = full_mr.get("head_pipeline")
            if hp and isinstance(hp, dict) and hp.get("status") == "failed":
                flags["failed_pipe"] = True

        # Accuracy fix: Only flag as 'bad' if we got a valid response showing 0 time.
        # If fetch failed (ts is None), we don't flag to avoid false positives.
        if ts and isinstance(ts, dict) and ts.get("total_time_spent", 0) == 0:
            flags["no_time"] = True

        # Improved Issue Linking: Check linked issues list AND description for various patterns
        has_linked_issue = bool(iss)
        if not has_linked_issue:
            desc_total = (mr.get("description") or "") + " " + (full_mr.get("description") or "" if full_mr else "")
            # GitLab supports many patterns: #123, Related to #123, Fixes #123, etc.
            if re.search(r"(?:#\d+|fixes|closes|resolves|related to|refs)\s*#?\d+", desc_total, re.IGNORECASE):
                has_linked_issue = True

        if not has_linked_issue:
            flags["no_issues"] = True

        # Improved Unit Test Detection: Check BOTH new_path and old_path
        h_tests = False
        if chg and isinstance(chg, dict):
            for c in chg.get("changes", []):
                new_p = str(c.get("new_path","")).lower()
                old_p = str(c.get("old_path","")).lower()
                if "test" in new_p or "spec" in new_p or "test" in old_p or "spec" in old_p:
                    h_tests = True
                    break
        if not h_tests: flags["no_unit_tests"] = True

    except Exception as e:
        print(f"Error evaluating MR {iid} for {uname}: {e}")

    return uname, flags

async def _fetch_user_mrs(session: aiohttp.ClientSession, sem: asyncio.Semaphore, base_url: str, headers: dict, uname: str) -> list[dict]:
    api_base = f"{base_url}/api/v4"
    u_data = await fetch_json(session, f"{api_base}/users", sem, headers=headers, params={"username": uname})
    if not u_data:
        return []

    uid = u_data[0]["id"]
    # Accuracy over Speed: Fetch 100 MRs instead of 20
    mrs = await fetch_json(session, f"{api_base}/merge_requests", sem, headers=headers, params={"author_id": str(uid), "scope": "all", "per_page": "100", "page": "1"})

    if not mrs:
        return []

    for mr in mrs:
        mr["_username"] = uname
    return mrs

async def _run_batch(client, usernames: list[str]) -> list[dict]:
    result_map = {u: {**_ZERO_ROW, "Username": u} for u in usernames}

    base_url = client.base_url.rstrip("/")
    headers = client.headers

    # 25 concurrent connections is highly optimal and stays below typical GitLab rate limits
    sem = asyncio.Semaphore(25)
    connector = aiohttp.TCPConnector(limit=25, ssl=False)

    print(f"DEBUG: Starting async batch fetch for {len(usernames)} users...")

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Fetch all user MRs concurrently
        user_tasks = [_fetch_user_mrs(session, sem, base_url, headers, u) for u in usernames]
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
                # CRITICAL FIX: Only count BAD MR metrics for MRs that are actually Closed/Merged.
                # This ensures the totals align with the "Closed MRs" column.
                if f.get("is_closed"):
                    row["Closed MRs"] += 1
                    if f.get("no_desc"): row["No Description"] += 1
                    if f.get("improper_desc"): row["Improper Description"] += 1
                    if f.get("no_issues"): row["No Issues Linked"] += 1
                    if f.get("no_time"): row["No Time Spent"] += 1
                    if f.get("no_unit_tests"): row["No Unit Tests"] += 1
                    if f.get("failed_pipe"): row["Failed Pipeline"] += 1

    print(f"DEBUG: Async batch fetch complete. Results for {len(result_map)} users.")
    return sorted(result_map.values(), key=lambda r: r["Closed MRs"], reverse=True)

def fetch_all_bad_mrs(client, usernames: list[str]) -> list[dict]:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_run_batch(client, usernames))

def _check_user_compliance(client, username: str) -> dict:
    # Small wrapper for test suite compatibility
    res = fetch_all_bad_mrs(client, [username])
    return res[0] if res else {**_ZERO_ROW, "Username": username}
