import asyncio
import os
import re

from dotenv import load_dotenv

from internship_activity_tracker.infrastructure.gitlab.client import GitLabClient

load_dotenv()

SEMANTIC_REGEX = r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?: "


async def diagnose(username):
    url = os.getenv("GITLAB_URL")
    token = os.getenv("GITLAB_TOKEN")
    client = GitLabClient(url, token)

    # Resolve User ID
    print(f"DEBUG: Resolving user '{username}'")
    u_data = await client._async_request("GET", "/users", params={"username": username})
    if not u_data:
        print(f"User {username} not found")
        return
    user_id = u_data[0]["id"]

    # Get MRs
    print(f"DEBUG: Fetching MRs for user_id {user_id}")
    mrs = await client._async_request(
        "GET", "/merge_requests", params={"author_id": user_id, "scope": "all", "per_page": 20}
    )
    if not mrs:
        print(f"No MRs found for {username}")
        return

    print(f"\n--- DIAGNOSTIC FOR {username} (Top 20 MRs) ---")

    for mr in mrs:
        iid = mr["iid"]
        pid = mr["project_id"]
        mr_author_id = mr["author"]["id"]
        state = mr["state"]
        is_closed = state in ("merged", "closed")

        print(f"\nMR !{iid} (State: {state})")

        # --- NOTES CHECK ---
        notes = await client._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/notes")
        has_external_review = False
        notes_count = 0
        if notes:
            for n in notes:
                if not n.get("system"):
                    notes_count += 1
                    if n["author"]["id"] != mr_author_id:
                        has_external_review = True

        upvotes = mr.get("upvotes", 0)
        if upvotes > 0:
            has_external_review = True

        # --- SEMANTIC CHECK ---
        commits = await client._async_request("GET", f"/projects/{pid}/merge_requests/{iid}/commits")
        has_semantic = False
        if commits:
            for c in commits:
                msg = c.get("message", "").lower()
                if re.match(SEMANTIC_REGEX, msg):
                    has_semantic = True
                    break

        if not has_semantic:
            title = mr.get("title", "").lower()
            if re.match(SEMANTIC_REGEX, title):
                has_semantic = True

        print(f"  Closed/Merged: {is_closed}")
        print(f"  Notes Count (Human): {notes_count}")
        print(f"  External Review: {has_external_review}")
        print(f"  Semantic Commits: {has_semantic}")


if __name__ == "__main__":
    import sys

    uname = sys.argv[1] if len(sys.argv) > 1 else "saikrishna_b"
    asyncio.run(diagnose(uname))
