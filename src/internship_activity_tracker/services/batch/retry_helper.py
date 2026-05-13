"""
Retry logic for GitLab API calls with exponential backoff.
No Streamlit dependencies.
"""

import logging
import time

logger = logging.getLogger(__name__)


def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    """Attempt to fetch a project from GitLab with retries on transient network errors.

    Args:
        gl_client: GitLab client instance (glabflow wrapper)
        path_or_id: Project path (string) or ID (integer)
        retries: Number of retry attempts
        backoff: Base backoff in seconds (multiplied by 2^(attempt-1))

    Returns:
        Project data (dict) on success
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            # Use the wrapper's _get method
            encoded = str(path_or_id).replace("/", "%2F")
            return gl_client._get(f"/projects/{encoded}")
        except Exception as e:
            last_exc = e
            # Immediate fail on 404
            if "404" in str(e) or "Not Found" in type(e).__name__:
                raise

            if attempt == retries:
                raise

            sleep_for = backoff * (2 ** (attempt - 1))
            logger.warning(f"Retry {attempt}/{retries} for {path_or_id} in {sleep_for}s: {e}")
            time.sleep(sleep_for)

    if last_exc:
        raise last_exc
