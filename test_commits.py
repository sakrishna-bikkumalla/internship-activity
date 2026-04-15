import os

from dotenv import load_dotenv

from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient
from gitlab_compliance_checker.infrastructure.gitlab.commits import get_user_commits
from gitlab_compliance_checker.infrastructure.gitlab.projects import get_user_projects
from gitlab_compliance_checker.infrastructure.gitlab.users import get_user_by_username

load_dotenv()
url = os.getenv("GITLAB_URL", "https://code.swecha.org")
token = os.getenv("GITLAB_TOKEN")

client = GitLabClient(base_url=url, private_token=token)

print("Fetching user Saiharshavardhan...")
user = get_user_by_username(client, "Saiharshavardhan")
print(f"User object: name='{user.get('name')}', username='{user.get('username')}', email='{user.get('email')}'")

print("\nFetching projects...")
projs = get_user_projects(client, user["id"], user["username"])
all_projs = projs["all"]
print(f"Found {len(all_projs)} projects.")

if all_projs:
    print(f"\nChecking commits for first project {all_projs[0]['id']} - {all_projs[0].get('name')}")
    all_commits, counts, stats = get_user_commits(client, user, [all_projs[0]])
    print(f"Stats: {stats}")
    print(f"Total returned commits from custom function: {len(all_commits)}")

    # Raw fetch
    pid = all_projs[0]["id"]
    api_params = {"all": "true", "with_stats": "false"}
    commits_data = client._run_sync(
        client._async_get_paginated(
            f"/projects/{pid}/repository/commits",
            params=api_params,
            per_page=100,
            max_pages=2,
        )
    )
    print(f"\nRaw commits fetched: {len(commits_data)}")
    if commits_data:
        print("First 10 commits:")
        for c in commits_data[:10]:
            print(f"Commit: {c.get('short_id')} by {c.get('author_name')} ({c.get('author_email')})")
