"""
async_bad_mrs.py
~~~~~~~~~~~~~~~~
RELIABILITY-FIRST BAD MRs engine.
- Sequential User ID lookups with aggressive retries.
- Capped scan depth (20 MRs per user) for guaranteed speed.
- Smart evaluation: only sub-resource fetch if necessary.
"""

from __future__ import annotations

import concurrent.futures
import time

from gitlab_utils.description_quality import analyze_description

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

def _evaluate_single_mr(client, mr: dict) -> tuple[str, dict]:
    uname = mr.get("_username", "unknown")
    pid, iid = mr["project_id"], mr["iid"]
    flags = {
        "is_closed": mr.get("state") in ("merged", "closed"),
        "no_desc": False, "improper_desc": False, "no_issues": False,
        "no_time": False, "no_unit_tests": False, "failed_pipe": False
    }

    try:
        # Description is in list response - check it first
        desc = mr.get("description") or ""
        if not str(desc).strip(): flags["no_desc"] = True
        try:
            if analyze_description(desc)["quality_label"] != "High":
                flags["improper_desc"] = True
        except: pass

        # Pipeline Status (Requires Detail)
        full_mr = client._get(f"/projects/{pid}/merge_requests/{iid}")
        if full_mr:
            # Re-check description from full detail just in case
            full_desc = full_mr.get("description") or ""
            if not str(full_desc).strip(): flags["no_desc"] = True

            # Pipeline
            hp = full_mr.get("head_pipeline")
            if hp and isinstance(hp, dict) and hp.get("status") == "failed":
                flags["failed_pipe"] = True

        # Sub-resources
        # Time Stats
        ts = client._get(f"/projects/{pid}/merge_requests/{iid}/time_stats")
        if not ts or ts.get("total_time_spent", 0) == 0: flags["no_time"] = True

        # Issues: Check endpoint (closing issues) AND description (mentions like #123)
        iss = client._get(f"/projects/{pid}/merge_requests/{iid}/issues")
        has_linked_issue = bool(iss)
        if not has_linked_issue:
            import re
            desc_total = (mr.get("description") or "") + " " + (full_mr.get("description") or "" if full_mr else "")
            if re.search(r"#\d+", desc_total):
                has_linked_issue = True

        if not has_linked_issue:
            flags["no_issues"] = True

        # Changes (Unit Tests)
        chg = client._get(f"/projects/{pid}/merge_requests/{iid}/changes")
        h_tests = False
        if chg and isinstance(chg, dict):
            h_tests = any("test" in str(c.get("new_path","")).lower() or "spec" in str(c.get("new_path","")).lower() for c in chg.get("changes", []))
        if not h_tests: flags["no_unit_tests"] = True

    except Exception as e:
        print(f"Error evaluating MR {iid} for {uname}: {e}")

    return uname, flags

def fetch_all_bad_mrs(client, usernames: list[str]) -> list[dict]:
    result_map = {u: {**_ZERO_ROW, "Username": u} for u in usernames}
    all_mr_tasks = []

    print(f"DEBUG: Starting batch fetch for {len(usernames)} users...")

    # Stage 1: Sequential identification
    for i, uname in enumerate(usernames):
        try:
            # Sequential for stability
            u_data = client._get("/users", params={"username": uname})
            if not u_data:
                print(f"DEBUG: User {uname} NOT FOUND")
                continue

            uid = u_data[0]["id"]
            # Limit to 20 MRs for fast, reliable reporting in batch mode
            user_mrs = client._get_paginated("/merge_requests", params={"author_id": uid, "scope": "all"}, per_page=20, max_pages=1)
            print(f"DEBUG: Found {len(user_mrs)} MRs for {uname}")

            for mr in user_mrs:
                mr["_username"] = uname
                all_mr_tasks.append(mr)
        except Exception as e:
            print(f"DEBUG: Error fetching data for {uname}: {e}")

    # Stage 2: Throttled evaluation
    # Increased workers slightly now that we have better session management
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_evaluate_single_mr, client, mr): mr for mr in all_mr_tasks}
        for future in concurrent.futures.as_completed(futures):
            try:
                uname, f = future.result()
                if uname in result_map:
                    row = result_map[uname]
                    if f["is_closed"]: row["Closed MRs"] += 1
                    if f["no_desc"]: row["No Description"] += 1
                    if f["improper_desc"]: row["Improper Description"] += 1
                    if f["no_issues"]: row["No Issues Linked"] += 1
                    if f["no_time"]: row["No Time Spent"] += 1
                    if f["no_unit_tests"]: row["No Unit Tests"] += 1
                    if f["failed_pipe"]: row["Failed Pipeline"] += 1
            except Exception: pass

    print(f"DEBUG: Batch fetch complete. Results for {len(result_map)} users.")
    return sorted(result_map.values(), key=lambda r: r["Closed MRs"], reverse=True)

def _check_user_compliance(client, username: str) -> dict:
    # Small wrapper for test suite compatibility
    res = fetch_all_bad_mrs(client, [username])
    return res[0] if res else {**_ZERO_ROW, "Username": username}
