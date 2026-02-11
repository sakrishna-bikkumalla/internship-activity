import streamlit as st

@st.cache_data(ttl=60)
def read_file_content(project, file_path, ref):
    try:
        file = project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None
