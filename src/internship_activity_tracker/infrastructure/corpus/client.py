import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class CorpusClient:
    def __init__(self, base_url: str = "https://api.corpus.swecha.org"):
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
        token: str = data.get("access_token", "")
        if not token:
            raise Exception("Login failed: Access token not found in response.")

        self.token = token
        return token

    def _resolve_user_to_uuid(self, user_identifier: str) -> str:
        """Resolve a username to UUID if necessary.

        The /users/{user_identifier} endpoint accepts either username or UUID.
        The /records/ endpoint requires a UUID for user_id.

        Args:
            user_identifier: Either a username or UUID

        Returns:
            The user's UUID

        Raises:
            Exception if user not found or token missing
        """
        if not self.token:
            raise Exception("Authentication required. Please login first.")

        if UUID_PATTERN.match(user_identifier):
            return user_identifier

        url = f"{self.base_url}/api/v1/users/{user_identifier}"
        headers = {"Authorization": f"Bearer {self.token}"}
        logger.debug(f"[Corpus] Resolving user '{user_identifier}' to UUID via {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        user_data = response.json()
        user_id: str = user_data.get("id", "")
        logger.debug(f"[Corpus] User '{user_identifier}' resolved to UUID: {user_id}")
        if not user_id:
            raise Exception(f"Could not resolve user '{user_identifier}' to UUID")
        return user_id

    def fetch_records(
        self,
        user_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch Corpus records for a user, optionally filtered by date range.

        Args:
            user_id: Corpus user ID (or username)
            start_date: Start date in YYYY-MM-DD format (optional, filters client-side)
            end_date: End date in YYYY-MM-DD format (optional, filters client-side)

        Returns:
            List of record dicts containing standup entries

        API Endpoint: GET /api/v1/records/
        Query Params: user_id, media_type, skip, limit
        Headers: Authorization: Bearer {token}
        Note: date filtering is done client-side via published_date field
        """
        if not self.token:
            raise Exception("Authentication required. Please login first.")

        uuid_user_id = self._resolve_user_to_uuid(user_id)
        logger.debug(
            f"[Corpus] Fetching records for user_id={uuid_user_id}, start_date={start_date}, end_date={end_date}"
        )

        all_records: list[dict[str, Any]] = []
        skip = 0
        limit = 100

        while True:
            url = f"{self.base_url}/api/v1/records/"
            params: dict[str, Any] = {"user_id": uuid_user_id, "skip": skip, "limit": limit}
            headers = {"Authorization": f"Bearer {self.token}"}

            logger.debug(f"[Corpus] GET {url} params={params}")
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            if isinstance(data, dict):
                records = data.get("records", [])
            else:
                records = data if isinstance(data, list) else []
            logger.debug(f"[Corpus] Fetched {len(records)} records (skip={skip}, limit={limit})")
            if not records:
                break
            all_records.extend(records)
            if len(records) < limit:
                break
            skip += limit

        logger.debug(f"[Corpus] Total records fetched: {len(all_records)}")
        if all_records:
            sample = all_records[0]
            logger.debug(f"[Corpus] Sample record keys: {list(sample.keys())}")
            logger.debug(f"[Corpus] Sample record: {sample}")

        if start_date or end_date:
            filtered: list[dict[str, Any]] = []
            for record in all_records:
                # Defensive check: ensure record belongs to the requested user
                rec_user_id = record.get("user_id")
                if rec_user_id and rec_user_id != uuid_user_id:
                    logger.warning(
                        f"[Corpus] Skipping record {record.get('id')} - user_id mismatch: {rec_user_id} != {uuid_user_id}"
                    )
                    continue

                published = record.get("published_date", "")
                if not isinstance(published, str) or not published:
                    created_at = record.get("created_at", "")
                    published = created_at[:10] if isinstance(created_at, str) and created_at else ""

                if isinstance(published, str) and published:
                    if start_date and published < start_date:
                        continue
                    if end_date and published > end_date:
                        continue
                filtered.append(record)
            logger.debug(
                f"[Corpus] Date filtering: {len(all_records)} -> {len(filtered)} records (start={start_date}, end={end_date})"
            )
            return filtered

        return all_records

    def extract_audio_urls(self, records: list[dict[str, Any]]) -> list[str]:
        """Extract audio file URLs from Corpus records.

        Args:
            records: List of record dicts from fetch_records

        Returns:
            List of audio file URLs where media_type is "audio" (or all file_urls if no media_type specified)
        """
        logger.debug(f"[Corpus] extract_audio_urls called with {len(records)} records")
        audio_urls = [
            record["file_url"]
            for record in records
            if record.get("file_url") and (record.get("media_type") is None or record.get("media_type") == "audio")
        ]
        logger.debug(f"[Corpus] Extracted {len(audio_urls)} audio URLs")
        for i, url in enumerate(audio_urls):
            logger.debug(f"[Corpus] Audio URL {i + 1}: {url}")
        return audio_urls

    def extract_all_media(self, records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Extract and classify all media files from Corpus records by type.

        Classifies each record into one of four buckets: audio, image, video, file.
        Classification is first attempted via the record's ``media_type`` field; if
        that is absent the file extension is used as a fallback.

        Args:
            records: List of record dicts from fetch_records

        Returns:
            Dict with keys "audio", "image", "video", "file", each mapping to a
            list of dicts: {url, filename, media_type, created_at, published_date}
        """
        IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff"}
        VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
        AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".opus", ".weba"}

        buckets: dict[str, list[dict[str, Any]]] = {
            "audio": [],
            "image": [],
            "video": [],
            "file": [],
        }

        for record in records:
            url = record.get("file_url", "")
            if not url:
                continue

            media_type: str = (record.get("media_type") or "").lower().strip()

            # Determine bucket
            if media_type in ("audio",):
                bucket = "audio"
            elif media_type in ("image", "photo", "picture"):
                bucket = "image"
            elif media_type in ("video",):
                bucket = "video"
            else:
                # Fallback: guess from file extension
                import os

                ext = os.path.splitext(url.split("?")[0])[-1].lower()
                if ext in AUDIO_EXTS:
                    bucket = "audio"
                elif ext in IMAGE_EXTS:
                    bucket = "image"
                elif ext in VIDEO_EXTS:
                    bucket = "video"
                else:
                    bucket = "file"

            entry: dict[str, Any] = {
                "url": url,
                "filename": record.get("file_name")
                or record.get("filename")
                or url.split("/")[-1].split("?")[0]
                or "file",
                "media_type": bucket,
                "created_at": record.get("created_at", ""),
                "published_date": record.get("published_date", ""),
            }
            buckets[bucket].append(entry)

        logger.debug(
            f"[Corpus] extract_all_media: audio={len(buckets['audio'])}, "
            f"image={len(buckets['image'])}, video={len(buckets['video'])}, "
            f"file={len(buckets['file'])}"
        )
        return buckets
