"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Timezone-aware epoch used as the default `published` so sorting never mixes
# naive and aware datetimes (all sources return aware datetimes).
_AWARE_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class JobItem:
    """A single job listing from one of the sources."""
    title: str
    url: str
    company: str
    location: str
    salary_min: int
    salary_max: int
    tags: list[str] = field(default_factory=list)
    description: str = ""
    published: datetime = field(default_factory=lambda: _AWARE_EPOCH)
    source_name: str = ""        # module key, e.g. "remoteok"

    def searchable_text(self) -> str:
        """Lowercased text blob used for keyword matching (title+company+tags)."""
        parts = [self.title or "", self.company or ""]
        parts.extend(self.tags or [])
        return " ".join(parts).lower()
