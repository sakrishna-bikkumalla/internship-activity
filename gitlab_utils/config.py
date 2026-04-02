import os
from typing import Any, Dict, List

# Path to data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Batch Definitions (Empty by default, can be populated from data/ or external sources)
BATCH_CONFIG: Dict[str, Any] = {}


def load_usernames_from_file(file_path: str) -> List[str]:
    """Loads usernames from a text file, one per line."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as f:
        return [line.strip() for line in f if line.strip()]
