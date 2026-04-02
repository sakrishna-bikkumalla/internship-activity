import logging
import os

from gitlab_compliance_checker.infrastructure.gitlab import users
from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient

logging.basicConfig(level=logging.DEBUG)

url = os.getenv("GITLAB_URL", "https://code.swecha.org")
token = os.getenv("GITLAB_TOKEN", "")
client = GitLabClient(url, token)

print("users.py:")
user = users.get_user_by_username(client, "lakshy")
print(user)

print("batch:")
try:
    res = client.batch_evaluate_mrs(["lakshy"])
    print(res)
except Exception as e:
    print(f"ERROR: {e}")

