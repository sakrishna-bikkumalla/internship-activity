import logging
from typing import Any, AsyncGenerator

import aiohttp

logger = logging.getLogger(__name__)
_GQL_TIMEOUT = aiohttp.ClientTimeout(total=30.0)


def _parse_gid(gid: str | int | None) -> int | None:
    """Convert 'gid://gitlab/Project/123' → 123, or pass through plain integers."""
    if gid is None:
        return None
    if isinstance(gid, int):
        return gid
    try:
        return int(gid.split("/")[-1])
    except (ValueError, IndexError):
        return None


class GitLabGraphQLClient:
    """
    Thin aiohttp-based client for GitLab's GraphQL API.
    Runs on the same GlobalBridge background loop as the REST client.
    """

    def __init__(self, base_url: str, token: str, is_oauth: bool = False):
        self.endpoint = f"{base_url.rstrip('/')}/api/graphql"
        if is_oauth:
            self._headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
        else:
            self._headers = {
                "Content-Type": "application/json",
                "PRIVATE-TOKEN": token,
            }
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "GitLabGraphQLClient":
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=10)
        self._session = aiohttp.ClientSession(timeout=_GQL_TIMEOUT, connector=connector)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def query(self, gql: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query. Returns the `data` dict (never raises on GQL errors)."""
        if not self._session:
            raise RuntimeError("GitLabGraphQLClient not initialized — call __aenter__ first")
        payload: dict[str, Any] = {"query": gql, "variables": variables or {}}
        async with self._session.post(self.endpoint, json=payload, headers=self._headers) as resp:
            resp.raise_for_status()
            result: dict = await resp.json(content_type=None)
        if "errors" in result:
            for err in result.get("errors", []):
                logger.warning("GraphQL error: %s", err.get("message", err))
        return result.get("data") or {}

    async def paginate(
        self,
        gql: str,
        variables: dict,
        page_info_path: list[str],
        nodes_path: list[str],
    ) -> AsyncGenerator[list[Any], None]:
        """
        Cursor-based pagination helper.
        Yields each page's `nodes` list until hasNextPage is False.
        `page_info_path` and `nodes_path` are key sequences from the data root.
        """
        variables = {**variables}
        while True:
            data = await self.query(gql, variables)

            nodes_obj: Any = data
            for key in nodes_path:
                nodes_obj = (nodes_obj or {}).get(key) or {}
            nodes: list = nodes_obj if isinstance(nodes_obj, list) else []
            yield nodes

            pi_obj: Any = data
            for key in page_info_path:
                pi_obj = (pi_obj or {}).get(key) or {}
            if not pi_obj.get("hasNextPage") or not pi_obj.get("endCursor"):
                break
            variables["after"] = pi_obj["endCursor"]
