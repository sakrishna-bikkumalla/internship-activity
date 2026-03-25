import asyncio
import os

import aiohttp

from gitlab_utils.client import GitLabClient


async def fetch_json(session, url, headers, params=None):
    print(f"DEBUG FETCH: {url} {params}")
    async with session.get(url, headers=headers, params=params, ssl=False) as resp:
        print(f"HTTP {resp.status}")
        if resp.status == 200:
            return await resp.json()
        text = await resp.text()
        print(f"Error {resp.status}: {text}")
        return None


async def main():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    url = os.getenv("GITLAB_URL", "https://code.swecha.org")
    token = os.getenv("GITLAB_TOKEN")
    if not token:
        print("NO TOKEN IN ENV!")
        return

    client = GitLabClient(url, token)
    headers = client.headers
    api_base = f"{client.base_url.rstrip('/')}/api/v4"

    async with aiohttp.ClientSession() as session:
        u_data = await fetch_json(session, f"{api_base}/users", headers, {"username": "prav2702"})
        if u_data and isinstance(u_data, list):
            uid = u_data[0]["id"]
            mrs = await fetch_json(
                session, f"{api_base}/merge_requests", headers, {"author_id": uid, "scope": "all", "per_page": 5}
            )
            print(f"MRs found: {len(mrs) if mrs else 0}")
        else:
            print("USER FETCH FAILED")


if __name__ == "__main__":
    asyncio.run(main())
