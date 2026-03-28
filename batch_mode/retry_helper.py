"""
Retry logic for GitLab API calls with exponential backoff.
No Streamlit dependencies.
"""

import http.client
import time

from gitlab import GitlabGetError


def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    """Attempt to fetch a project from GitLab with retries on transient network errors.

    Args:
        gl_client: GitLab client instance
        path_or_id: Project path (string) or ID (integer)
        retries: Number of retry attempts
        backoff: Base backoff in seconds (multiplied by 2^(attempt-1))

    Returns:
        Project object on success

    Raises:
        Last exception if all retries fail
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return gl_client.projects.get(int(path_or_id) if str(path_or_id).isdigit() else path_or_id)
        except GitlabGetError as e:
            # If it's a 404-like error (project not found), re-raise immediately
            last_exc = e
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
            last_exc = e
            if type(e).__name__ not in ("RequestException", "ConnectionError", "Timeout"):
                if not isinstance(e, (OSError, http.client.RemoteDisconnected)):
                    raise
            if attempt == retries:
                raise
            sleep_for = backoff * (2 ** (attempt - 1))
            time.sleep(sleep_for)
    # If loop exits without returning, raise the last exception
    if last_exc:
        raise last_exc
