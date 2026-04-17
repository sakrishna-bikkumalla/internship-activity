from typing import Any


class CorpusClient:
    def __init__(self, base_url: str = "https://corpus.example.com"):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def login(self, phone: str, password: str) -> str:
        raise NotImplementedError("Corpus login not yet implemented.")

    def fetch_records(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("Corpus record fetching not yet implemented.")

    def extract_audio_urls(self, records: list[dict[str, Any]]) -> list[str]:
        raise NotImplementedError("Audio URL extraction not yet implemented.")
