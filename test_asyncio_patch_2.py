import asyncio
from unittest.mock import patch

import nest_asyncio


def target_func():
    nest_asyncio.apply()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return loop


def test_patch():
    # Patch it in the module where target_func will look for it
    with patch("nest_asyncio.apply"):
        with patch("asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no loop")
            target_func()
            assert mock_get.called
            print("Success!")


if __name__ == "__main__":
    test_patch()
