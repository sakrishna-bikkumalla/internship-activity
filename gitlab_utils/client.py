import time

import gitlab
import requests
import streamlit as st

# Use a global session for connection pooling
_SESSION = requests.Session()

def safe_api_call(func, *args, **kwargs):
    """
    Safe wrapper for GitLab API calls with aggressive retry logic and 429 handling.
    """
    max_retries = 5 # Increased retries
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response.status_code == 429:
                retry_after = e.response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait_limit = int(retry_after)
                        if wait_limit > 60:
                            raise Exception(f"GitLab API Rate Limit Exceeded. Please try again after {wait_limit} seconds.")
                    except ValueError:
                        pass

                # Aggressive backoff for 429
                wait_time = (5 * (attempt + 1))
                print(f"Rate limited (429) on {e.request.url}. Waiting {wait_time}s...")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception("GitLab API Rate Limit Exceeded (429 Too Many Requests). Max retries reached.")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return []
        except (requests.exceptions.ConnectionError, ConnectionResetError) as e:
            # Server is dropping connections, wait and retry
            wait_time = 5 * (attempt + 1)
            print(f"Connection Reset/Error: {e}. Waiting {wait_time}s...")
            time.sleep(wait_time)
            continue
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            print(f"FAILED API CALL: {e}") # Diagnostic
            return []
    return []

class GitLabClient:
    def __init__(self, base_url, private_token):
        self.base_url = base_url.rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.headers = {"PRIVATE-TOKEN": private_token}
        self.private_token = private_token
        self.error_msg = None
        self._client = None

    @property
    def client(self):
        """Lazy-loaded python-gitlab client."""
        if self._client is None:
            st.sidebar.write(f"  - Lazy init: connecting to {self.base_url}...")
            try:
                self._client = gitlab.Gitlab(
                    url=self.base_url,
                    private_token=self.private_token,
                    timeout=5,
                    ssl_verify=False
                )
                # Note: Skipping .auth() here as well to keep it responsive.
                st.sidebar.write("  - Lazy init: Success")
            except Exception as e:
                self.error_msg = str(e)
                st.sidebar.write(f"  - Lazy init: FAILED: {e}")
                self._client = None
        return self._client

    def _request(self, method, endpoint, params=None):
        url = f"{self.api_base}{endpoint}"
        def make_request():
            response = _SESSION.request(
                method, url, headers=self.headers, params=params, timeout=30, verify=False
            )
            response.raise_for_status()
            if response.status_code == 204: return None
            return response.json()
        return safe_api_call(make_request)

    def _get(self, endpoint, params=None):
        return self._request("GET", endpoint, params=params)

    def _get_paginated(self, endpoint, params=None, per_page=100, max_pages=10):
        all_items = []
        for page in range(1, max_pages + 1):
            p_params = {**(params or {}), "per_page": per_page, "page": page}
            batch = self._get(endpoint, params=p_params)
            if not isinstance(batch, list) or not batch: break
            all_items.extend(batch)
            if len(batch) < per_page: break
        return all_items
