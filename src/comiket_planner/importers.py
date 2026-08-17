from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .core import now_iso, source_ref, stable_id

ALIASES = {
    "circle_name": ("circle_name", "サークル名", "circle"),
    "creator_name": ("creator_name", "作家名", "creator"),
    "space_code": ("space_code", "配置", "space"),
    "priority": ("priority", "優先度"),
    "genre_short": ("genre_short", "一言ジャンル", "ジャンル"),
    "notes": ("notes", "メモ", "備考"),
    "visit_status": ("visit_status", "訪問状態", "状態"),
    "x_handle": ("x_handle", "X", "Twitter", "handle"),
    "item_name": ("item_name", "購入予定", "商品名"),
    "price": ("price", "価格", "小計"),
    "purchase_state": ("purchase_state", "購入状態"),
}

PRIORITY_VALUES = {"最優先": "A", "高": "A", "中": "B", "低": "C", "未設定": "unassigned"}
STATUS_VALUES = {"未訪問": "unvisited", "購入済": "purchased", "売切れ": "sold_out", "見送り": "skipped"}


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
        name = str(_value(row, "circle_name", "unknown")).strip() or "unknown"
        handle = str(_value(row, "x_handle", "")).strip().lstrip("@") or None
        key = (handle or name).casefold()
        if key not in by_key:
            visit_id = row.get("visit_id") or stable_id(event_id, handle, name)
            circle = {
                "visit_id": visit_id,
                "circle_name": name,
                "creator_name": str(_value(row, "creator_name", "")).strip() or None,
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
