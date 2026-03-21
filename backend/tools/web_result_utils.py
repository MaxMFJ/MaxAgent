"""
Utilities for compacting web-search style payloads before they enter LLM context.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def truncate_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def extract_highlights_from_text(text: Any, max_points: int = 3, max_chars: int = 180) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    normalized = re.sub(r"\s+", " ", raw)
    pieces = re.split(r"(?<=[。！？.!?])\s+|\n+", normalized)
    highlights: List[str] = []
    for piece in pieces:
        candidate = piece.strip(" -\t")
        if len(candidate) < 20:
            continue
        short = truncate_text(candidate, max_chars)
        if short and short not in highlights:
            highlights.append(short)
        if len(highlights) >= max_points:
            break
    return highlights


def compact_web_payload(
    data: Any,
    *,
    max_items: int = 5,
    snippet_chars: int = 220,
    excerpt_chars: int = 800,
    include_content: bool = True,
) -> Any:
    """Compress common web-search payloads into a smaller structured summary."""
    if not isinstance(data, dict):
        return data

    if _looks_like_web_list_payload(data, "results"):
        return _compact_search_list_payload(
            data,
            key="results",
            max_items=max_items,
            snippet_chars=snippet_chars,
        )

    if _looks_like_web_list_payload(data, "news"):
        return _compact_search_list_payload(
            data,
            key="news",
            max_items=max_items,
            snippet_chars=snippet_chars,
        )

    if "findings" in data and isinstance(data.get("findings"), list):
        return _compact_research_payload(
            data,
            max_items=max_items,
            snippet_chars=snippet_chars,
            excerpt_chars=excerpt_chars,
            include_content=include_content,
        )

    if "text" in data and isinstance(data.get("text"), str):
        compact = dict(data)
        compact["text"] = truncate_text(compact.get("text"), excerpt_chars)
        compact["char_count"] = compact.get("char_count") or len(str(data.get("text") or ""))
        return compact

    if "content" in data and isinstance(data.get("content"), str):
        compact = dict(data)
        compact["content"] = truncate_text(compact.get("content"), excerpt_chars)
        return compact

    return data


def _compact_search_list_payload(
    data: Dict[str, Any],
    *,
    key: str,
    max_items: int,
    snippet_chars: int,
) -> Dict[str, Any]:
    items = data.get(key) or []
    compact_items: List[Dict[str, Any]] = []
    domains: List[str] = []

    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("href") or "")
        domain = _extract_domain(url)
        if domain and domain not in domains:
            domains.append(domain)
        compact_item = {
            "title": truncate_text(item.get("title") or url, 120),
            "url": url,
            "snippet": truncate_text(item.get("snippet") or item.get("body") or item.get("description"), snippet_chars),
        }
        if item.get("source"):
            compact_item["source"] = item.get("source")
        if item.get("published_date"):
            compact_item["published_date"] = item.get("published_date")
        compact_items.append(compact_item)

    compact = {
        "query": data.get("query", ""),
        key: compact_items,
        "count": data.get("count", len(items)),
        "source": data.get("source", ""),
        "backend": data.get("backend", ""),
    }
    if domains:
        compact["domains"] = domains[:max_items]
    return compact


def _compact_research_payload(
    data: Dict[str, Any],
    *,
    max_items: int,
    snippet_chars: int,
    excerpt_chars: int,
    include_content: bool,
) -> Dict[str, Any]:
    findings = data.get("findings") or []
    compact_findings: List[Dict[str, Any]] = []
    domains: List[str] = []
    all_highlights: List[str] = []

    for item in findings[:max_items]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        domain = _extract_domain(url)
        if domain and domain not in domains:
            domains.append(domain)
        entry = {
            "title": truncate_text(item.get("title") or url, 120),
            "url": url,
            "snippet": truncate_text(item.get("snippet"), snippet_chars),
            "highlights": _normalize_highlights(item, max_chars=snippet_chars),
        }
        if include_content and item.get("content_excerpt"):
            entry["content_excerpt"] = truncate_text(item.get("content_excerpt"), excerpt_chars)
        if item.get("source"):
            entry["source"] = item.get("source")
        if item.get("read_backend"):
            entry["read_backend"] = item.get("read_backend")
        compact_findings.append(entry)
        all_highlights.extend(entry["highlights"])

    compact = {
        "query": data.get("query", ""),
        "findings": compact_findings,
        "count": data.get("count", len(findings)),
        "search_backend": data.get("search_backend", data.get("backend", "")),
        "research_backend": data.get("research_backend", ""),
        "summary": truncate_text(data.get("summary"), 900),
        "domains": domains[:max_items],
    }
    unique_highlights: List[str] = []
    for hl in all_highlights:
        if hl and hl not in unique_highlights:
            unique_highlights.append(hl)
    if unique_highlights:
        compact["highlights"] = unique_highlights[:6]
    return compact


def _normalize_highlights(item: Dict[str, Any], max_chars: int) -> List[str]:
    raw = item.get("highlights")
    if isinstance(raw, list):
        values = [truncate_text(v, max_chars) for v in raw if str(v).strip()]
        return values[:3]
    return extract_highlights_from_text(item.get("content_excerpt") or item.get("snippet"), max_chars=max_chars)


def _extract_domain(url: str) -> Optional[str]:
    if not url or "://" not in url:
        return None
    host = url.split("://", 1)[1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _looks_like_web_list_payload(data: Dict[str, Any], key: str) -> bool:
    items = data.get(key)
    if not isinstance(items, list):
        return False
    if any(marker in data for marker in ("query", "source", "backend")):
        return True
    for item in items[:3]:
        if isinstance(item, dict) and any(k in item for k in ("url", "href", "link", "title", "snippet")):
            return True
    return False
