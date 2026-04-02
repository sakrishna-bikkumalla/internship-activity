import json
from typing import Any, Optional

import yaml


def parse_yaml(content: str) -> Optional[Any]:
    """Safely parse YAML content."""
    if not content:
        return None
    try:
        return yaml.safe_load(content)
    except Exception:
        return None


def parse_json(content: str) -> Optional[Any]:
    """Safely parse JSON content."""
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        return None
