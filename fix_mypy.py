with open("gitlab_utils/pipeline_checker.py", "r") as f:
    code = f.read()
code = code.replace("result = {", "result: Dict[str, Any] = {")
with open("gitlab_utils/pipeline_checker.py", "w") as f:
    f.write(code)
