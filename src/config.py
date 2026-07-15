"""Configuration loading from config.yml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class Filters:
    keyword_include: List[str] = field(default_factory=list)
    keyword_exclude: List[str] = field(default_factory=list)
    salary_min: int = 0


@dataclass
class Config:
    sources: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    filters: Filters = field(default_factory=Filters)
    max_total_items: int = 50
    max_push_items: int = 15
    timezone_offset: int = 8

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        f_raw = data.get("filters", {}) or {}
        return cls(
            sources=data.get("sources", {}) or {},
            filters=Filters(
                keyword_include=[str(x) for x in f_raw.get("keyword_include", [])],
                keyword_exclude=[str(x) for x in f_raw.get("keyword_exclude", [])],
                salary_min=int(f_raw.get("salary_min", 0) or 0),
            ),
            max_total_items=int(data.get("max_total_items", 50)),
            max_push_items=int(data.get("max_push_items", 15)),
            timezone_offset=int(data.get("timezone_offset", 8)),
        )

    def is_enabled(self, source_name: str) -> bool:
        block = self.sources.get(source_name, {})
        return bool(block.get("enabled", False))
