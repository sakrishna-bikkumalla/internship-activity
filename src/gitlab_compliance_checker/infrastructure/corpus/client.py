import requests
from typing import Any


class CorpusClient:
    def __init__(self, base_url: str = "https://corpus.example.com"):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def login(self, phone: str, password: str) -> str:
        """Authenticate with Corpus API using phone/password.

        Args:
            phone: Phone number (e.g., "+1234567890")
            password: Password

        Returns:
            JWT access token string

        Raises:
            Exception if login fails

        API Endpoint: POST /api/v1/auth/login
        Request Body: { "phone": "...", "password": "..." }
        Response: { "access_token": "..." }
        """
        url = f"{self.base_url}/api/v1/auth/login"
        payload = {"phone": phone, "password": password}
        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise Exception("Login failed: Access token not found in response.")

        self.token = token
        return token

    def fetch_records(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch Corpus records for a user within a date range.

        Args:
            user_id: Corpus user ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of record dicts containing standup entries

        API Endpoint: GET /api/v1/records/
        Query Params: user_id, start_date, end_date
        Headers: Authorization: Bearer {token}

        Expected Response Structure:
        {
            "records": [
                {
                    "id": "...",
                    "user_id": "...",
                    "date": "YYYY-MM-DD",
                    "file_url": "https://...",  # ← This is the audio URL
                    ...
                },
                ...
            ]
        }
        """
        if not self.token:
            raise Exception("Authentication required. Please login first.")

        url = f"{self.base_url}/api/v1/records/"
        params = {"user_id": user_id, "start_date": start_date, "end_date": end_date}
        headers = {"Authorization": f"Bearer {self.token}"}

        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()
        return data.get("records", [])

    def extract_audio_urls(self, records: list[dict[str, Any]]) -> list[str]:
        """Extract audio file URLs from Corpus records.

        Args:
            records: List of record dicts from fetch_records

        Returns:
            List of audio file URLs (file_url field)
        """
        return [record["file_url"] for record in records if "file_url" in record and record["file_url"]]
