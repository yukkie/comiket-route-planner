from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .core import now_iso, source_ref, stable_id

ALIASES = {
    "circle_name": ("circle_name", "サークル名", "circle"),
    "creator_name": ("creator_name", "作家名", "creator", "名前"),
    "space_code": ("space_code", "配置", "space"),
    "priority": ("priority", "優先度"),
    "genre_short": ("genre_short", "一言ジャンル", "ジャンル"),
    "notes": ("notes", "メモ", "備考"),
    "visit_status": ("visit_status", "訪問状態", "状態"),
    "x_handle": ("x_handle", "X", "Xアカウント", "Twitter", "handle"),
    "item_name": ("item_name", "購入予定", "商品名"),
    "price": ("price", "価格", "小計"),
    "purchase_state": ("purchase_state", "購入状態"),
}

PRIORITY_VALUES = {"最優先": "A", "高": "A", "中": "B", "低": "C", "未設定": "unassigned"}
STATUS_VALUES = {"未訪問": "unvisited", "購入済": "purchased", "売切れ": "sold_out", "見送り": "skipped"}
HANDLE_RE = re.compile(r"(?:https?://(?:www\.)?(?:x|twitter)\.com/|@)([A-Za-z0-9_]{1,15})", re.IGNORECASE)


def _value(row: dict[str, Any], field: str, default: Any = "") -> Any:
    for key in ALIASES[field]:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _price(value: Any) -> int | None:
    if value in (None, "", "不明", "unknown"):
        return None
    cleaned = str(value).replace("¥", "").replace("￥", "").replace(",", "").replace("円", "").strip()
    return int(cleaned)


def normalize_x_handle(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = HANDLE_RE.search(text)
    handle = match.group(1) if match else text.lstrip("@").split()[0]
    return handle if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) else None


def _row_handle(row: dict[str, Any]) -> str | None:
    # A URL identifies exactly one account, while the text column may contain
    # several aliases separated by slashes or newlines.
    for key in ("x_handle", "X", "Xアカウント", "Twitter", "handle"):
        handle = normalize_x_handle(row.get(key))
        if handle:
            return handle
    return None


def import_previous(path: str | Path, event_id: str) -> list[dict[str, Any]]:
    target = Path(path)
    if target.suffix.lower() == ".json":
        with target.open(encoding="utf-8-sig") as handle:
            raw = json.load(handle)
        rows = raw.get("circles", []) if isinstance(raw, dict) else raw
    else:
        with target.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if not isinstance(rows, list):
        raise ValueError("Previous-list JSON must be an array or an EventPlan object")

    ref = source_ref(target, "previous_list")
    circles: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        creator = str(_value(row, "creator_name", "")).strip() or None
        name = str(_value(row, "circle_name", creator or "unknown")).strip() or creator or "unknown"
        handle = _row_handle(row)
        key = (handle or name).casefold()
        if key not in by_key:
            visit_id = row.get("visit_id") or stable_id(event_id, handle, name)
            circle = {
                "visit_id": visit_id,
                "circle_name": name,
                "creator_name": creator,
                "aliases": list(row.get("aliases", [])),
                "x_user_id": row.get("x_user_id"),
                "x_handle": handle,
                "space_code": str(_value(row, "space_code", "")).strip() or None,
                "hall": row.get("hall"),
                "placement_type": row.get("placement_type", "unknown"),
                "priority": PRIORITY_VALUES.get(str(_value(row, "priority", "unassigned")), str(_value(row, "priority", "unassigned"))),
                "genre_short": str(_value(row, "genre_short", "")).strip(),
                "visit_status": STATUS_VALUES.get(str(_value(row, "visit_status", "unvisited")), str(_value(row, "visit_status", "unvisited"))),
                "notes": str(_value(row, "notes", "")).strip(),
                "items": [],
                "field_meta": {},
                "source_refs": [ref],
            }
            for field in ("priority", "genre_short", "notes", "visit_status"):
                if circle[field] not in (None, "", "unassigned", "unvisited"):
                    circle["field_meta"][field] = {"origin": "previous_list", "confidence": 1.0, "manually_confirmed": True, "updated_at": now_iso()}
            by_key[key] = circle
            circles.append(circle)
        circle = by_key[key]
        item_name = str(_value(row, "item_name", "")).strip()
        if item_name:
            circle["items"].append({
                "item_id": row.get("item_id") or stable_id(circle["visit_id"], item_name),
                "name": item_name,
                "variant": row.get("variant"),
                "price": _price(_value(row, "price", None)),
                "currency": "JPY",
                # A previous event's selection is useful evidence, but is not a
                # confirmed decision for the new event.
                "purchase_state": "candidate",
                "availability": row.get("availability", "unknown"),
                "age_rating": row.get("age_rating", "unknown"),
                "bundle_components": list(row.get("bundle_components", [])),
                "source_refs": [ref],
            })
    return circles


def import_follow_lists(
    paths: list[str | Path],
    event_id: str,
    profile_pattern: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize one or more follow-list exports keyed by display name.

    The source export contains profile metadata, not confirmed circle names. The
    display name is therefore stored as creator_name and only used as a clearly
    marked provisional circle_name until participation data supplies the real one.
    """
    matcher = re.compile(profile_pattern, re.IGNORECASE) if profile_pattern else None
    by_handle: dict[str, dict[str, Any]] = {}
    input_records = selected_records = duplicate_records = 0
    for raw_path in paths:
        path = Path(raw_path)
        with path.open(encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Follow-list JSON must be an object: {path}")
        ref = source_ref(path, "x_follow_list")
        for value in payload.values():
            input_records += 1
            if not isinstance(value, dict):
                continue
            profile_text = "\n".join(str(value.get(field, "")) for field in ("name", "desc"))
            if matcher and not matcher.search(profile_text):
                continue
            x_handle = normalize_x_handle(value.get("id") or value.get("url"))
            if not x_handle:
                continue
            selected_records += 1
            key = x_handle.casefold()
            if key in by_handle:
                duplicate_records += 1
                circle = by_handle[key]
                known = {item.get("source_id") for item in circle["source_refs"]}
                if ref["source_id"] not in known:
                    circle["source_refs"].append(ref)
                circle.setdefault("follow_source_files", []).append(path.name)
                continue
            creator_name = str(value.get("name") or x_handle).strip()
            by_handle[key] = {
                "visit_id": stable_id(event_id, "x_handle", key),
                "circle_name": creator_name,
                "creator_name": creator_name,
                "aliases": [],
                "x_user_id": None,
                "x_handle": x_handle,
                "x_url": str(value.get("url") or f"https://x.com/{x_handle}"),
                "space_code": None,
                "hall": None,
                "placement_type": "unknown",
                "priority": "unassigned",
                "genre_short": "",
                "visit_status": "unvisited",
                "notes": "",
                "items": [],
                "profile_description": str(value.get("desc") or ""),
                "profile_image_url": value.get("img"),
                "circle_name_confirmed": False,
                "follow_source_files": [path.name],
                "field_meta": {
                    "creator_name": {"origin": "x_follow_list", "confidence": 1.0, "manually_confirmed": False, "updated_at": now_iso()},
                    "circle_name": {"origin": "creator_name_placeholder", "confidence": 0.0, "manually_confirmed": False, "updated_at": now_iso()},
                },
                "source_refs": [ref],
            }
    return list(by_handle.values()), {
        "input_records": input_records,
        "selected_records": selected_records,
        "unique_handles": len(by_handle),
        "duplicate_records": duplicate_records,
        "profile_pattern": profile_pattern,
    }


def enrich_with_previous(
    candidates: list[dict[str, Any]],
    previous: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Carry only user-authored priority and short genre across events."""
    by_handle = {str(circle.get("x_handle") or "").casefold(): circle for circle in candidates if circle.get("x_handle")}
    matched_handles: set[str] = set()
    unmatched: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    enriched_fields = 0
    for old in previous:
        key = str(old.get("x_handle") or "").casefold()
        if not key or key not in by_handle:
            unmatched.append({"creator_name": old.get("creator_name") or old.get("circle_name"), "x_handle": old.get("x_handle")})
            continue
        matched_handles.add(key)
        current = by_handle[key]
        for field in ("priority", "genre_short"):
            value = old.get(field)
            if value in (None, "", "unassigned"):
                continue
            existing = current.get(field)
            if existing not in (None, "", "unassigned", value):
                conflicts.append({"x_handle": old.get("x_handle"), "field": field, "existing": existing, "incoming": value})
                continue
            current[field] = value
            current.setdefault("field_meta", {})[field] = {
                "origin": "previous_list",
                "confidence": 1.0,
                "manually_confirmed": True,
                "updated_at": now_iso(),
            }
            enriched_fields += 1
        current.setdefault("previous_event_refs", []).extend(old.get("source_refs", []))
    return candidates, {
        "previous_records": len(previous),
        "matched_handles": len(matched_handles),
        "unmatched_previous": unmatched,
        "conflicts": conflicts,
        "enriched_fields": enriched_fields,
    }


def append_previous_only(
    candidates: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    event_id: str,
) -> tuple[list[dict[str, Any]], int]:
    """Append previous-list entries missing from the filtered follow candidates."""
    handles = {str(circle.get("x_handle") or "").casefold() for circle in candidates if circle.get("x_handle")}
    names = {str(circle.get("creator_name") or "").strip().casefold() for circle in candidates if circle.get("creator_name")}
    added = 0
    for old in previous:
        creator = str(old.get("creator_name") or old.get("circle_name") or "").strip()
        handle = normalize_x_handle(old.get("x_handle"))
        if not creator or creator == "unknown":
            continue
        if (handle and handle.casefold() in handles) or creator.casefold() in names:
            continue
        key = handle.casefold() if handle else creator.casefold()
        candidates.append({
            "visit_id": stable_id(event_id, "previous", key),
            "circle_name": creator,
            "creator_name": creator,
            "aliases": [],
            "x_user_id": None,
            "x_handle": handle,
            "x_url": f"https://x.com/{handle}" if handle else None,
            "space_code": None,
            "hall": None,
            "placement_type": "unknown",
            "priority": old.get("priority", "unassigned"),
            "genre_short": old.get("genre_short", ""),
            "visit_status": "unvisited",
            "notes": "",
            "items": [],
            "circle_name_confirmed": False,
            "candidate_origin": "previous_list_only",
            "field_meta": {
                "circle_name": {"origin": "creator_name_placeholder", "confidence": 0.0, "manually_confirmed": False, "updated_at": now_iso()},
                **({"priority": {"origin": "previous_list", "confidence": 1.0, "manually_confirmed": True, "updated_at": now_iso()}} if old.get("priority") not in (None, "", "unassigned") else {}),
                **({"genre_short": {"origin": "previous_list", "confidence": 1.0, "manually_confirmed": True, "updated_at": now_iso()}} if old.get("genre_short") else {}),
            },
            "source_refs": list(old.get("source_refs", [])),
        })
        if handle:
            handles.add(handle.casefold())
        names.add(creator.casefold())
        added += 1
    return candidates, added
