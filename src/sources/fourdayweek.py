"""4 Day Week job source.

https://4dayweek.io/api - returns a JSON dict with a `jobs` array. Jobs
offering a 4-day work week.

Job fields: id_str, title, slug, url, description, category, role, level,
hours, reduced_hours, is_remote, location_city, location_country,
location_continent, posted, company_name.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from typing import List

import requests

from ..items import JobItem
from .base import BaseJobSource

_API_URL = "https://4dayweek.io/api"
_HEADERS = {"User-Agent": "job-scraper/1.0 (daily digest)"}
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_dt(s) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


class FourDayWeekSource(BaseJobSource):
    name = "fourdayweek"
    display_name = "4 Day Week"
    emoji = "🗓️"

    def fetch(self, config: dict) -> List[JobItem]:
        max_results: int = int(config.get("max_results", 25))
        try:
            resp = requests.get(_API_URL, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[warn] fourdayweek fetch failed: {e}", file=sys.stderr)
            return []

        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        items: List[JobItem] = []
        for j in jobs:
            url = j.get("url")
            title = j.get("title")
            if not url or not title:
                continue
            # Build a readable location string.
            loc_parts = [p for p in [
                j.get("location_city", ""),
                j.get("location_country", ""),
            ] if p]
            location = ", ".join(loc_parts) or (
                "Remote" if j.get("is_remote") else "")
            # 4DayWeek has no explicit salary field in the listing; leave 0.
            desc = _TAG_RE.sub("", j.get("description", "") or "")
            tags = []
            if j.get("category"):
                tags.append(str(j["category"]))
            if j.get("role"):
                tags.append(str(j["role"]))
            if j.get("level"):
                tags.append(str(j["level"]))
            items.append(JobItem(
                title=title,
                url=url,
                company=j.get("company_name", "") or "",
                location=location,
                salary_min=0,
                salary_max=0,
                tags=tags[:10],
                description=desc,
                published=_parse_dt(j.get("posted")),
                source_name=self.name,
            ))
            if len(items) >= max_results:
                break
        print(f"[info] fourdayweek: {len(items)} jobs", file=sys.stderr)
        return items
