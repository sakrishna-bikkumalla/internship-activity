# gitlab_compliance_checker/infrastructure/gitlab/retry_helper.py

import http.client
import time

from gitlab import GitlabGetError


def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    """
    Fetch GitLab project with retry logic for transient failures.
    """

    for attempt in range(1, retries + 1):
        try:
            return gl_client.projects.get(int(path_or_id) if str(path_or_id).isdigit() else path_or_id)

        except GitlabGetError as e:
            if getattr(e, "response", None) is not None and e.response.status_code == 404:
                raise
            if attempt == retries:
                raise

        except (
            ConnectionResetError,
            ConnectionAbortedError,
            OSError,
            http.client.RemoteDisconnected,
            Exception,
        ) as e:
            if type(e).__name__ not in ("RequestException", "ConnectionError", "Timeout"):
                if not isinstance(e, (OSError, http.client.RemoteDisconnected)):
                    raise
            if attempt == retries:
                raise
            time.sleep(backoff * (2 ** (attempt - 1)))
