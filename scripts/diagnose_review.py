import asyncio
import os
import re

import aiohttp
from dotenv import load_dotenv

from gitlab_utils.client import GitLabClient

load_dotenv()

SEMANTIC_REGEX = r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\(.*?\))?!?: "

async def fetch_json(session, url, headers, params=None):
    async with session.get(url, headers=headers, params=params, ssl=False) as resp:
        if resp.status == 200:
            return await resp.json()
        return None

async def diagnose(username):
    url = os.getenv("GITLAB_URL")
    token = os.getenv("GITLAB_TOKEN")
    client = GitLabClient(url, token)
    headers = client.headers
    api_base = f"{client.base_url.rstrip('/')}/api/v4"

    async with aiohttp.ClientSession() as session:
        # Get User ID
        print(f"DEBUG: Resolving user '{username}'")
        u_data = await fetch_json(session, f"{api_base}/users", headers, {"username": username})
        if not u_data:
            print(f"User {username} not found")
            return
        user_id = u_data[0]['id']

        # Get MRs
        print(f"DEBUG: Fetching MRs for user_id {user_id}")
        mrs = await fetch_json(session, f"{api_base}/merge_requests", headers, {"author_id": user_id, "scope": "all", "per_page": 20})
        if not mrs:
            print(f"No MRs found for {username}")
            return

        print(f"\n--- DIAGNOSTIC FOR {username} (Top 20 MRs) ---")

        for mr in mrs:
            iid = mr['iid']
            pid = mr['project_id']
            mr_author_id = mr['author']['id']
            state = mr['state']
            is_closed = state in ('merged', 'closed')

            print(f"\nMR !{iid} (State: {state})")

            # --- NOTES CHECK ---
            notes = await fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}/notes", headers)
            has_external_review = False
            notes_count = 0
            if notes:
                for n in notes:
                    if not n.get('system'):
                        notes_count += 1
                        if n['author']['id'] != mr_author_id:
                            has_external_review = True

            upvotes = mr.get('upvotes', 0)
            if upvotes > 0: has_external_review = True

            # --- SEMANTIC CHECK ---
            commits = await fetch_json(session, f"{api_base}/projects/{pid}/merge_requests/{iid}/commits", headers)
            has_semantic = False
            if commits:
                for c in commits:
                    msg = c.get('message', '').lower()
                    if re.match(SEMANTIC_REGEX, msg):
                        has_semantic = True
                        break

            if not has_semantic:
                title = mr.get('title', '').lower()
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
