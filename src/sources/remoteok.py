"""RemoteOK job source.

https://remoteok.com/api - returns a JSON list. The first element is metadata
(last_updated/legal), the rest are job objects. Remote tech jobs worldwide.

Job fields: slug, id, epoch, date, company, position, tags, description,
location, salary_min, salary_max, url.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import List

import requests

from ..items import JobItem
from .base import BaseJobSource

_API_URL = "https://remoteok.com/api"
_HEADERS = {"User-Agent": "job-scraper/1.0 (daily digest)"}


def _parse_dt(s) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        # RemoteOK uses ISO8601 with offset, e.g. 2026-07-13T21:02:42+00:00
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class RemoteOKSource(BaseJobSource):
    name = "remoteok"
    display_name = "RemoteOK"
    emoji = "🌐"

    def fetch(self, config: dict) -> List[JobItem]:
        max_results: int = int(config.get("max_results", 30))
        try:
            resp = requests.get(_API_URL, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[warn] remoteok fetch failed: {e}", file=sys.stderr)
            return []

        if not isinstance(data, list):
            print(f"[warn] remoteok: unexpected type {type(data).__name__}",
                  file=sys.stderr)
            return []

        items: List[JobItem] = []
        for entry in data:
            # Skip the metadata element (no 'position' key) and non-job dicts.
            if not isinstance(entry, dict):
                continue
            position = entry.get("position")
            url = entry.get("url")
            if not position or not url:
                continue
            items.append(JobItem(
                title=position,
                url=url,
                company=entry.get("company", "") or "",
                location=entry.get("location", "") or "",
                salary_min=_to_int(entry.get("salary_min")),
                salary_max=_to_int(entry.get("salary_max")),
                tags=[str(t) for t in entry.get("tags", []) or []][:10],
                description=entry.get("description", "") or "",
                published=_parse_dt(entry.get("date")),
                source_name=self.name,
            ))
            if len(items) >= max_results:
                break
        print(f"[info] remoteok: {len(items)} jobs", file=sys.stderr)
        return items
