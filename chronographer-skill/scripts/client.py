"""Chronographer client helpers (minimal)

A small, dependency-light helper used by the skill to call the Chronographer API.
"""

import os
import requests


class ChronoClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or os.getenv("CHRONO_API_URL", "http://localhost:8000")
        self.api_key = api_key or os.getenv("CHRONO_API_KEY")
        if not self.api_key:
            raise RuntimeError("CHRONO_API_KEY not set")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def list_upcoming(self, start_iso, end_iso, display_tz=None, include_overdue=False):
        params = {
            "start": start_iso,
            "end": end_iso,
            "include_overdue": str(include_overdue).lower(),
        }
        if display_tz:
            params["display_tz"] = display_tz
        r = requests.get(
            f"{self.base_url}/api/v1/upcoming", headers=self.headers, params=params
        )
        r.raise_for_status()
        return r.json()

    def create_task(self, payload):
        r = requests.post(
            f"{self.base_url}/api/v1/tasks", json=payload, headers=self.headers
        )
        r.raise_for_status()
        return r.json()

    def complete_task(
        self,
        task_id,
        completed_at=None,
        notes=None,
        metadata=None,
        idempotency_key=None,
        occurrence_id=None,
    ):
        payload = {}
        if completed_at is not None:
            payload["completed_at"] = completed_at
        if notes is not None:
            payload["notes"] = notes
        if metadata is not None:
            payload["metadata"] = metadata
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        if occurrence_id is not None:
            payload["occurrence_id"] = occurrence_id
        r = requests.post(
            f"{self.base_url}/api/v1/tasks/{task_id}/completions",
            json=payload,
            headers=self.headers,
        )
        r.raise_for_status()
        return r.json()

    def get_last_completion(self, task_id):
        r = requests.get(
            f"{self.base_url}/api/v1/tasks/{task_id}/last", headers=self.headers
        )
        r.raise_for_status()
        return r.json()

    def get_next(self, task_id):
        r = requests.get(
            f"{self.base_url}/api/v1/tasks/{task_id}/next", headers=self.headers
        )
        r.raise_for_status()
        return r.json()
