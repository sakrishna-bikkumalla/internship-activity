"""
File reading utilities for GitLab projects.
Supports both cached (Streamlit) and non-cached reads.
"""


def read_file_content_no_cache(project, file_path, ref):
    """Read file content from GitLab project without caching.
    
    Args:
        project: GitLab project object
        file_path: Path to file in repository
        ref: Branch/tag reference
        
    Returns:
        File content as string, or None if file not found/error
    """
    try:
        file = project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None


def read_file_content_cached(project, file_path, ref):
    """Read file content from GitLab project with Streamlit caching.
    
    Requires Streamlit to be available.
    
    Args:
        project: GitLab project object
        file_path: Path to file in repository
        ref: Branch/tag reference
        
    Returns:
        File content as string, or None if file not found/error
    """
    try:
        import streamlit as st
        
        @st.cache_data(ttl=60)
        def _read_cached(_project, file_path, ref):
            try:
                file = _project.files.get(file_path=file_path, ref=ref)
                return file.decode().decode("utf-8")
            except Exception:
                return None
        
        return _read_cached(project, file_path, ref)
    except ImportError:
        # Fallback to non-cached version if Streamlit not available
        return read_file_content_no_cache(project, file_path, ref)


# Alias for backward compatibility
def read_file_content(project, file_path, ref):
    """Legacy alias - uses cached read with Streamlit if available."""
    return read_file_content_cached(project, file_path, ref)
