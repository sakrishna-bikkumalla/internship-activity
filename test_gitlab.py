import os

import gitlab
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("GITLAB_URL", "https://code.swecha.org")
token = os.getenv("GITLAB_TOKEN")
gl = gitlab.Gitlab(url, private_token=token)
res = gl.http_get("/users", query_data={"username": "lakshy"})
print(type(res))
print(res)
