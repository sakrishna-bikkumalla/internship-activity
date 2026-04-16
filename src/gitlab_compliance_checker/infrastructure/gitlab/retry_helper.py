import logging
import time

logger = logging.getLogger(__name__)


def get_project_with_retries(gl_client, path_or_id, retries=3, backoff=1):
    """
    Fetch GitLab project with retry logic for transient failures.
    `gl_client` is a GitLabClient wrapper.
    """
    for attempt in range(1, retries + 1):
        try:
            # path_or_id can be 'group/project' or 123
            encoded = str(path_or_id).replace("/", "%2F")
            return gl_client._get(f"/projects/{encoded}")

        except Exception as e:
            # Check for 404
            if "404" in str(e) or "Not Found" in type(e).__name__:
                raise

            if attempt == retries:
                raise

            logger.warning(f"Retry {attempt}/{retries} for project {path_or_id} due to: {e}")
            time.sleep(backoff * (2 ** (attempt - 1)))
