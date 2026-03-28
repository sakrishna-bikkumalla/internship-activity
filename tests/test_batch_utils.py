from unittest.mock import MagicMock, patch

import pytest
from gitlab import GitlabGetError

from batch_mode import file_reader, retry_helper

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
    # Mock streamlit success (line 41-49)
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
    gl_client.projects.get.return_value = "project_obj"

    res = retry_helper.get_project_with_retries(gl_client, "123")
    assert res == "project_obj"
    gl_client.projects.get.assert_called_with(123)


def test_get_project_with_retries_404():
    gl_client = MagicMock()
    # Mocking GitlabGetError with response attribute
    err = GitlabGetError()
    err.response = MagicMock(status_code=404)
    gl_client.projects.get.side_effect = err

    with pytest.raises(GitlabGetError):
        retry_helper.get_project_with_retries(gl_client, "path/to/proj")


def test_get_project_with_retries_transient_then_success():
    gl_client = MagicMock()
    gl_client.projects.get.side_effect = [ConnectionResetError(), "success"]

    with patch("time.sleep"):  # avoid actual sleeping
        res = retry_helper.get_project_with_retries(gl_client, "123", retries=2)
        assert res == "success"
        assert gl_client.projects.get.call_count == 2


def test_get_project_with_retries_all_fail():
    gl_client = MagicMock()
    
    class RequestException(Exception):
        pass
        
    gl_client.projects.get.side_effect = RequestException("timeout")

    with patch("time.sleep"):
        with pytest.raises(RequestException):
            retry_helper.get_project_with_retries(gl_client, "123", retries=2)


def test_get_project_with_retries_gitlab_other_error():
    gl_client = MagicMock()
    err = GitlabGetError()
    err.response = MagicMock(status_code=500)
    gl_client.projects.get.side_effect = err

    with patch("time.sleep"):
        with pytest.raises(GitlabGetError):
            retry_helper.get_project_with_retries(gl_client, "123", retries=2)
