from gitlab_utils.async_bad_mrs import fetch_all_bad_mrs
from gitlab_utils.client import GitLabClient


def main():
    client = GitLabClient()
    # Assuming client is initialized automatically from .env
    # We will test for a single user
    res = fetch_all_bad_mrs(client, ["prav2702"])
    for row in res:
        print(row)


if __name__ == "__main__":
    main()
