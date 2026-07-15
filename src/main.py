"""Job tracker entry point.

Two modes:
  - Subscription (default): `python -m src.main`
    Fetch all jobs from each enabled source, apply filters, dedup, archive to
    digests/YYYY-MM-DD.md, push a summary to WeChat.
  - Search: `python -m src.main --search QUERY`
    Keep only jobs whose title/company/tags match the keyword (on top of the
    config filters), archive to digests/search-{QUERY}-{YYYY-MM-DD}.md.

GitHub Actions: the workflow_dispatch `search` input maps to --search.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from html import unescape
from pathlib import Path

from .config import Config, Filters
from .items import JobItem
from .notifiers import notify
from .sources import discover_sources

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SAFE_FN_RE = re.compile(r"[^a-zA-Z0-9一-鿿_-]")


def _strip_html(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _safe_filename_part(query: str) -> str:
    return _SAFE_FN_RE.sub("_", query).strip("_")[:30] or "query"


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yml"
DIGESTS_DIR = REPO_ROOT / "digests"


def _today(tz_offset: int) -> date:
    tz = timezone(timedelta(hours=tz_offset))
    return datetime.now(tz).date()


def apply_filters(items: list[JobItem], filters: Filters,
                  search_query: str = "") -> list[JobItem]:
    """Filter jobs by config filters + optional search keyword.

    - keyword_include: keep only if any term appears in searchable text.
    - keyword_exclude: drop if any term appears.
    - salary_min: drop if salary_max is set and below threshold (0 = unknown).
    - search_query (CLI): keep only if it appears in searchable text.
    """
    inc = [t.lower() for t in filters.keyword_include]
    exc = [t.lower() for t in filters.keyword_exclude]
    sq = search_query.lower().strip()

    out: list[JobItem] = []
    for it in items:
        text = it.searchable_text()
        if exc and any(t in text for t in exc):
            continue
        if inc and not any(t in text for t in inc):
            continue
        if sq and sq not in text:
            continue
        if filters.salary_min > 0 and it.salary_max > 0 \
                and it.salary_max < filters.salary_min:
            continue
        out.append(it)
    return out


def _fmt_salary(smin: int, smax: int) -> str:
    if smin <= 0 and smax <= 0:
        return ""
    if smin == smax:
        return f"${smin:,}"
    return f"${smin:,}-${smax:,}"


def _fmt_job_line_md(it: JobItem) -> list[str]:
    """One job rendered as a markdown bullet block."""
    lines = [f"- **[{it.title}]({it.url})**"]
    meta_parts = [it.company] if it.company else []
    if it.location:
        meta_parts.append(it.location)
    sal = _fmt_salary(it.salary_min, it.salary_max)
    if sal:
        meta_parts.append(sal)
    if meta_parts:
        lines.append(f"  - {' | '.join(meta_parts)}")
    if it.tags:
        lines.append(f"  - tags: {', '.join(it.tags)}")
    desc = _strip_html(it.description)
    if desc:
        lines.append(f"  - {desc[:200]}{'...' if len(desc) > 200 else ''}")
    return lines


def generate_markdown(items: list[JobItem], today: date,
                      source_meta: dict, search_query: str = "") -> str:
    if search_query:
        title = f"# 职位搜索「{search_query}」- {today.isoformat()}"
        intro = f"> 共找到 {len(items)} 个匹配职位。"
    else:
        title = f"# 每日职位摘要 - {today.isoformat()}"
        intro = f"> 共 {len(items)} 个职位，按数据源分类。"
    lines = [title, "", intro, ""]

    by_source: dict[str, list[JobItem]] = defaultdict(list)
    for it in items:
        by_source[it.source_name].append(it)

    for source_name in sorted(by_source.keys()):
        meta = source_meta.get(source_name, {})
        emoji = meta.get("emoji", "")
        display = meta.get("display_name", source_name)
        src_items = by_source[source_name]
        lines.append(f"## {emoji} {display} ({len(src_items)})")
        lines.append("")
        for it in src_items:
            lines.extend(_fmt_job_line_md(it))
            lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_webhook_message(items: list[JobItem], today: date,
                             max_items: int, source_meta: dict,
                             search_query: str = "") -> str:
    if search_query:
        lines = [f"## 职位搜索「{search_query}」（{len(items)} 条）", ""]
    else:
        lines = [f"## 每日职位摘要 {today.isoformat()}（{len(items)} 条）", ""]

    by_source: dict[str, list[JobItem]] = defaultdict(list)
    for it in items:
        by_source[it.source_name].append(it)

    pushed = 0
    for source_name in sorted(by_source.keys()):
        if pushed >= max_items:
            break
        meta = source_meta.get(source_name, {})
        emoji = meta.get("emoji", "")
        display = meta.get("display_name", source_name)
        lines.append(f"{emoji} {display}")
        for it in by_source[source_name]:
            if pushed >= max_items:
                break
            company = f" @ {it.company}" if it.company else ""
            lines.append(f"- [{it.title}{company}]({it.url})")
            pushed += 1
        lines.append("")

    if len(items) > pushed:
        lines.append(f"- ...及另外 {len(items) - pushed} 条")
        lines.append("")

    if search_query:
        fn = f"search-{_safe_filename_part(search_query)}-{today.isoformat()}.md"
        lines.append(f"> 完整列表见仓库 `digests/{fn}`")
    else:
        lines.append(f"> 完整列表见仓库 `digests/{today.isoformat()}.md`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Job tracker")
    parser.add_argument("--search", type=str, default="",
                        help="keyword search (empty = subscription mode)")
    args = parser.parse_args()
    search_query = (args.search or "").strip()

    config = Config.from_file(CONFIG_PATH)
    registry = discover_sources()
    mode = "search" if search_query else "subscription"
    print(f"[info] mode: {mode}"
          + (f" | query='{search_query}'" if search_query else ""),
          file=sys.stderr)
    print(f"[info] registered sources: {list(registry)}", file=sys.stderr)

    all_items: list[JobItem] = []
    source_meta: dict = {}
    for source_name, SourceClass in registry.items():
        if not config.is_enabled(source_name):
            print(f"[info] source '{source_name}' disabled, skipping",
                  file=sys.stderr)
            continue
        if source_name not in config.sources:
            print(f"[info] source '{source_name}' has no config block, "
                  f"skipping", file=sys.stderr)
            continue
        source = SourceClass()
        source_meta[source_name] = {
            "display_name": getattr(source, "display_name", source_name),
            "emoji": getattr(source, "emoji", ""),
        }
        print(f"[info] fetching source '{source_name}'...", file=sys.stderr)
        items = source.fetch(config.sources[source_name])
        print(f"[info] source '{source_name}': {len(items)} jobs (pre-filter)",
              file=sys.stderr)
        all_items.extend(items)

    # Apply config filters + search keyword.
    filtered = apply_filters(all_items, config.filters, search_query)
    print(f"[info] after filters: {len(filtered)} jobs", file=sys.stderr)

    if not filtered:
        print("[error] no jobs matched (after filters/search)", file=sys.stderr)
        return 1

    # Dedup by URL across sources.
    seen: set[str] = set()
    unique: list[JobItem] = []
    for it in filtered:
        if it.url in seen:
            continue
        seen.add(it.url)
        unique.append(it)

    # Sort newest-first, then cap total.
    unique.sort(key=lambda x: x.published, reverse=True)
    unique = unique[:config.max_total_items]

    today = _today(config.timezone_offset)
    markdown = generate_markdown(unique, today, source_meta, search_query)

    DIGESTS_DIR.mkdir(exist_ok=True)
    if search_query:
        out_name = (f"search-{_safe_filename_part(search_query)}-"
                    f"{today.isoformat()}.md")
        push_title = f"职位搜索「{search_query}」结果（{len(unique)} 条）"
    else:
        out_name = f"{today.isoformat()}.md"
        push_title = f"每日职位摘要 {today.isoformat()}（{len(unique)} 条）"
    output_path = DIGESTS_DIR / out_name
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[info] digest written to {output_path} ({len(unique)} jobs)",
          file=sys.stderr)

    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if webhook_url:
        msg = generate_webhook_message(unique, today, config.max_push_items,
                                       source_meta, search_query)
        notify(webhook_url, msg, push_title)
    else:
        print("[info] WEBHOOK_URL not set, skipping notification",
              file=sys.stderr)

    print(f"::notice::Digest generated: {out_name} ({len(unique)} jobs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
