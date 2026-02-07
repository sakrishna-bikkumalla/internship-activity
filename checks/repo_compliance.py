def check_repo_compliance(client, project_id):
    result = {
        "Project ID": project_id,
        "Project Name": "",
        "README Present": "No",
        "CI/CD Enabled": "No",
        "LICENSE Present": "No"
    }

    project = client.get_project(project_id)
    result["Project Name"] = project["name"]

    files = client.get_project_files(project_id)
    filenames = [f["name"].lower() for f in files]

    if any("readme" in f for f in filenames):
        result["README Present"] = "Yes"

    if ".gitlab-ci.yml" in filenames:
        result["CI/CD Enabled"] = "Yes"

    if any("license" in f for f in filenames):
        result["LICENSE Present"] = "Yes"

    return result
