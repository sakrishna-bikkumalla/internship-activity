import asyncio
from unittest.mock import MagicMock, patch

import nest_asyncio


def target_func():
    nest_asyncio.apply()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return loop


class TestAsyncioPatch2:
    def test_get_event_loop_success(self):
        mock_loop = MagicMock()
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            with patch("nest_asyncio.apply"):
                result = target_func()
                assert result == mock_loop

    def test_get_event_loop_runtime_error_creates_new(self):
        with patch("asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no running event loop")
            with patch("asyncio.new_event_loop", return_value=MagicMock()) as mock_new:
                with patch("nest_asyncio.apply"):
                    target_func()
                    assert mock_get.called
                    assert mock_new.called

    def test_nest_asyncio_apply_called(self):
        with patch("asyncio.get_event_loop", return_value=MagicMock()):
            with patch("nest_asyncio.apply") as mock_apply:
                target_func()
                mock_apply.assert_called_once()

    def test_nest_asyncio_apply_called_on_error(self):
        with patch("asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no running event loop")
            with patch("asyncio.new_event_loop", return_value=MagicMock()):
                with patch("nest_asyncio.apply") as mock_apply:
                    target_func()
                    mock_apply.assert_called_once()

    def test_multiple_calls_idempotency(self):
        mock_loop = MagicMock()
        with patch("asyncio.get_event_loop", return_value=mock_loop):
            with patch("nest_asyncio.apply"):
                result1 = target_func()
                result2 = target_func()
                result3 = target_func()
                assert result1 == mock_loop
                assert result2 == mock_loop
                assert result3 == mock_loop

    def test_new_event_loop_returned_on_error(self):
        mock_new_loop = MagicMock()
        with patch("asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no running event loop")
            with patch("asyncio.new_event_loop", return_value=mock_new_loop):
                with patch("nest_asyncio.apply"):
                    result = target_func()
                    assert result == mock_new_loop

    def test_both_get_and_new_called_on_error(self):
        with patch("asyncio.get_event_loop") as mock_get:
            mock_get.side_effect = RuntimeError("no running event loop")
            with patch("asyncio.new_event_loop", return_value=MagicMock()) as mock_new:
                with patch("nest_asyncio.apply"):
                    target_func()
                    assert mock_get.called
                    assert mock_new.called

    def test_nest_asyncio_apply_exception(self):
        with patch("asyncio.get_event_loop", return_value=MagicMock()):
            with patch("nest_asyncio.apply", side_effect=Exception("apply failed")):
                try:
                    target_func()
                except Exception:
                    pass

    def test_get_event_loop_with_none_result(self):
        with patch("asyncio.get_event_loop", return_value=None):
            with patch("nest_asyncio.apply"):
                result = target_func()
                assert result is None

    def test_different_runtime_error_messages(self):
        error_messages = [
            "no running event loop",
            "RuntimeError: Event loop is closed",
            " asyncio.get_event_loop() generator didn't yield",
        ]
        for msg in error_messages:
            with patch("asyncio.get_event_loop") as mock_get:
                mock_get.side_effect = RuntimeError(msg)
                with patch("asyncio.new_event_loop", return_value=MagicMock()):
                    with patch("nest_asyncio.apply"):
                        result = target_func()
                        assert result is not None

    def test_patching_order_matters(self):
        mock_loop = MagicMock()
        with patch("nest_asyncio.apply"):
            with patch("asyncio.get_event_loop", return_value=mock_loop):
                result = target_func()
                assert result == mock_loop
