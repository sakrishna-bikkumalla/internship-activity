from unittest.mock import MagicMock, patch

import pytest

# We remove 'from gitlab import GitlabGetError' as it is no longer available.
# We will use a generic Exception mock in tests that check for errors.
from internship_activity_tracker.services.batch import file_reader, retry_helper

# --- Tests for file_reader.py ---


def test_read_file_content_no_cache_success():
    project = MagicMock()
    file_mock = MagicMock()
    file_mock.decode.return_value = b"hello"
    project.files.get.return_value = file_mock

    res = file_reader.read_file_content_no_cache(project, "f.txt", "main")
    assert res == "hello"


def test_read_file_content_no_cache_fail():
    project = MagicMock()
    project.files.get.side_effect = Exception("404")
    assert file_reader.read_file_content_no_cache(project, "f.txt", "main") is None


def test_read_file_content_cached_no_streamlit():
    # If streamlit is not available (ImportError), it should fallback
    with patch(
        "builtins.__import__",
        side_effect=lambda name, *args, **kwargs: (
            (lambda: exec('raise ImportError("no st")'))() if name == "streamlit" else __import__(name, *args, **kwargs)
        ),
    ):
        project = MagicMock()
        file_mock = MagicMock()
        file_mock.decode.return_value = b"cached"
        project.files.get.return_value = file_mock

        # Should call read_file_content_no_cache
        res = file_reader.read_file_content(project, "f.txt", "main")
        assert res == "cached"


def test_read_file_content_cached_with_streamlit():
    # Mock streamlit success
    mock_st = MagicMock()

    # mock_st.cache_data is a decorator
    def mock_decorator(ttl=None):
        def wrapper(func):
            return func

        return wrapper

    mock_st.cache_data = mock_decorator

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        project = MagicMock()
        file_mock = MagicMock()
        file_mock.decode.return_value = b"st_cached"
        project.files.get.return_value = file_mock

        # Should use the cached function
        res = file_reader.read_file_content_cached(project, "f.txt", "main")
        assert res == "st_cached"


def test_read_file_content_cached_with_streamlit_fail():
    mock_st = MagicMock()
    mock_st.cache_data = lambda **kwargs: lambda f: f

    with patch.dict("sys.modules", {"streamlit": mock_st}):
        project = MagicMock()
        project.files.get.side_effect = Exception("fail")

        res = file_reader.read_file_content_cached(project, "f.txt", "main")
        assert res is None


# --- Tests for retry_helper.py ---


def test_get_project_with_retries_success():
    gl_client = MagicMock()
    # Updated to match gl_client._get call in retry_helper
    gl_client._get.return_value = {"id": 123, "name": "project_name"}

    res = retry_helper.get_project_with_retries(gl_client, "123")
    assert res == {"id": 123, "name": "project_name"}
    gl_client._get.assert_called_with("/projects/123")


def test_get_project_with_retries_404():
    gl_client = MagicMock()
    # In the new code, we raise Exception that contains "404" or is a specific NotFoundError
    err = Exception("404 Not Found")
    gl_client._get.side_effect = err

    with pytest.raises(Exception) as excinfo:
        retry_helper.get_project_with_retries(gl_client, "path/to/proj")
    assert "404" in str(excinfo.value)


def test_get_project_with_retries_transient_then_success():
    gl_client = MagicMock()
    gl_client._get.side_effect = [ConnectionResetError(), {"id": 123}]

    with patch("time.sleep"):  # avoid actual sleeping
        res = retry_helper.get_project_with_retries(gl_client, "123", retries=2)
        assert res == {"id": 123}
        assert gl_client._get.call_count == 2


def test_get_project_with_retries_all_fail():
    gl_client = MagicMock()

    class RequestError(Exception):
        pass

    gl_client._get.side_effect = RequestError("timeout")

    with patch("time.sleep"):
        with pytest.raises(RequestError):
            retry_helper.get_project_with_retries(gl_client, "123", retries=2)
