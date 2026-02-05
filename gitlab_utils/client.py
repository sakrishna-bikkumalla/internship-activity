import requests


class GitLabClient:
    def __init__(self, base_url, private_token):
        self.base_url = base_url.rstrip("/")
        self.headers = {"PRIVATE-TOKEN": private_token}

    def _get(self, endpoint):
        url = f"{self.base_url}/api/v4{endpoint}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    class users:
        @staticmethod
        def get_by_username(username):
            raise NotImplementedError("User API not implemented in minimal client.")

        @staticmethod
        def get_by_userid(user_id):
            raise NotImplementedError("User API not implemented in minimal client.")

        @staticmethod
        def get_user_project_count(user_id):
            return "N/A"

        @staticmethod
        def get_user_group_count(user_id):
            return "N/A"

        @staticmethod
        def get_user_issue_count(user_id):
            return "N/A"

        @staticmethod
        def get_user_mr_count(user_id):
            return "N/A"
