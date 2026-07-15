"""Remotive job source.

https://remotive.com/api/remote-jobs - returns a JSON dict with a `jobs`
array. Remote jobs across categories (dev, design, support, etc.).

Job fields: id, url, title, company_name, category, tags, job_type,
publication_date, candidate_required_location, salary, description.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from typing import List

import requests

from ..items import JobItem
from .base import BaseJobSource

_API_URL = "https://remotive.com/api/remote-jobs"
_HEADERS = {"User-Agent": "job-scraper/1.0 (daily digest)"}
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_dt(s) -> datetime:
    """Remotive dates are naive (no tz suffix, e.g. 2026-07-13T07:05:10).
    Treat as UTC to stay comparable with the other sources' aware datetimes.
    """
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _parse_salary(s) -> tuple[int, int]:
    """Best-effort parse of Remotive's free-text salary field into min/max."""
    if not s:
        return 0, 0
    nums = re.findall(r"[\d,]+", str(s))
    nums = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
    if not nums:
        return 0, 0
    return min(nums), max(nums)


class RemotiveSource(BaseJobSource):
    name = "remotive"
    display_name = "Remotive"
    emoji = "💼"

    def fetch(self, config: dict) -> List[JobItem]:
        max_results: int = int(config.get("max_results", 25))
        try:
            resp = requests.get(_API_URL, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[warn] remotive fetch failed: {e}", file=sys.stderr)
            return []

        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        items: List[JobItem] = []
        for j in jobs:
            url = j.get("url")
            title = j.get("title")
            if not url or not title:
                continue
            smin, smax = _parse_salary(j.get("salary"))
            # Remotive description is HTML; strip tags for a clean snippet.
            desc = _TAG_RE.sub("", j.get("description", "") or "")
            items.append(JobItem(
                title=title,
                url=url,
                company=j.get("company_name", "") or "",
                location=j.get("candidate_required_location", "") or "",
                salary_min=smin,
                salary_max=smax,
                tags=[str(t) for t in j.get("tags", []) or []][:10],
                description=desc,
                published=_parse_dt(j.get("publication_date")),
                source_name=self.name,
            ))
            if len(items) >= max_results:
                break
        print(f"[info] remotive: {len(items)} jobs", file=sys.stderr)
        return items
