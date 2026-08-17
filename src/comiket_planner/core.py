from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import EventPlan

PRIORITIES = {"A", "B", "C", "unassigned"}
VISIT_STATUSES = {"unvisited", "purchased", "sold_out", "skipped"}
PURCHASE_STATES = {"buy", "candidate", "skip"}
PLACEMENT_TYPES = {"shutter_front", "wall", "island_end", "island", "unknown"}
MANUAL_CIRCLE_FIELDS = ("priority", "genre_short", "notes", "visit_status")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def stable_id(*parts: object) -> str:
    value = "\x1f".join(str(part or "").strip().casefold() for part in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"comiket-route-planner:{value}"))


def new_plan(event_id: str, name: str | None = None, day: int | None = None) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "event": {
            "event_id": event_id,
            "name": name or event_id,
            "day": day,
            "event_date": None,
            "map_source_id": None,
        },
        "circles": [],
        "budget": calculate_budget([]),
        "generated_at": now_iso(),
    }


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def save_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def source_ref(path: str | Path, source_type: str) -> dict[str, Any]:
    target = Path(path)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "source_id": f"{source_type}-{digest[:16]}",
        "type": source_type,
        "locator": str(target),
        "captured_at": now_iso(),
        "content_hash": digest,
    }


def calculate_budget(circles: list[dict[str, Any]]) -> dict[str, Any]:
    planned = maximum = unknown_buy = unknown_candidate = 0
    unknown_items: list[dict[str, str]] = []
    for circle in circles:
        for item in circle.get("items", []):
            state = item.get("purchase_state", "skip")
            price = item.get("price")
            if state not in {"buy", "candidate"}:
                continue
            if price is None:
                if state == "buy":
                    unknown_buy += 1
                else:
                    unknown_candidate += 1
                unknown_items.append({
                    "visit_id": str(circle.get("visit_id", "")),
                    "circle_name": str(circle.get("circle_name", "unknown")),
                    "item_name": str(item.get("name", "unknown")),
                    "purchase_state": state,
                })
                continue
            if not isinstance(price, int) or isinstance(price, bool) or price < 0:
                continue
            maximum += price
            if state == "buy":
                planned += price
    return {
        "planned_total": planned,
        "max_total": maximum,
        "unknown_price_buy_count": unknown_buy,
        "unknown_price_candidate_count": unknown_candidate,
        "unknown_price_items": unknown_items,
    }


def _manual(field_meta: dict[str, Any], field: str) -> bool:
    meta = field_meta.get(field, {})
    return bool(meta.get("manually_confirmed") or meta.get("origin") == "user")


def _circle_keys(circle: dict[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for field in ("x_user_id", "x_handle", "visit_id"):
        value = str(circle.get(field) or "").strip().casefold()
        if field == "x_handle":
            value = value.lstrip("@")
        if value:
            keys.append((field, value))
    name = str(circle.get("circle_name") or "").strip().casefold()
    creator = str(circle.get("creator_name") or "").strip().casefold()
    if name:
        keys.append(("name", f"{name}\x1f{creator}"))
    return keys


def _merge_items(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], protect: bool) -> list[dict[str, Any]]:
    result = copy.deepcopy(existing)
    indexes: dict[tuple[str, str], int] = {}
    for i, item in enumerate(result):
        if item.get("item_id"):
            indexes[("id", str(item["item_id"]).strip().casefold())] = i
        if item.get("name"):
            indexes[("name", str(item["name"]).strip().casefold())] = i
    for candidate in incoming:
        keys = []
        if candidate.get("item_id"):
            keys.append(("id", str(candidate["item_id"]).strip().casefold()))
        if candidate.get("name"):
            keys.append(("name", str(candidate["name"]).strip().casefold()))
        match = next((indexes[key] for key in keys if key in indexes), None)
        if match is None:
            added = copy.deepcopy(candidate)
            added.setdefault("item_id", stable_id("item", candidate.get("name")))
            added.setdefault("purchase_state", "candidate")
            result.append(added)
            for key in keys:
                indexes[key] = len(result) - 1
            continue
        current = result[match]
        selected = current.get("purchase_state")
        current.update(copy.deepcopy(candidate))
        if protect and selected is not None:
            current["purchase_state"] = selected
    return result


def merge_plans(base: dict[str, Any], incoming: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Merge incoming records and protect manual decisions for the same event."""
    result = copy.deepcopy(base)
    same_event = base.get("event", {}).get("event_id") == incoming.get("event", {}).get("event_id")
    stats = {"added": 0, "updated": 0, "protected_fields": 0, "source_missing": 0}
    indexes: dict[tuple[str, str], int] = {}
    for i, circle in enumerate(result.get("circles", [])):
        for key in _circle_keys(circle):
            indexes[key] = i
    seen_indexes: set[int] = set()

    for candidate in incoming.get("circles", []):
        keys = _circle_keys(candidate)
        match = next((indexes[key] for key in keys if key in indexes), None)
        if match is None:
            added = copy.deepcopy(candidate)
            identity = keys[0] if keys else ("name", candidate.get("circle_name", "unknown"))
            added.setdefault("visit_id", stable_id(result["event"]["event_id"], identity[0], identity[1]))
            added["visit_status"] = "unvisited"
            for item in added.get("items", []):
                item.setdefault("item_id", stable_id(added["visit_id"], item.get("name")))
                if not same_event:
                    item["purchase_state"] = "candidate"
            result.setdefault("circles", []).append(added)
            match = len(result["circles"]) - 1
            for key in _circle_keys(added):
                indexes[key] = match
            seen_indexes.add(match)
            stats["added"] += 1
            continue

        seen_indexes.add(match)
        current = result["circles"][match]
        old_meta = copy.deepcopy(current.get("field_meta", {}))
        protected = {field: current.get(field) for field in MANUAL_CIRCLE_FIELDS if same_event and _manual(old_meta, field)}
        old_items = copy.deepcopy(current.get("items", []))
        old_sources = copy.deepcopy(current.get("source_refs", []))
        current.update(copy.deepcopy(candidate))
        current["items"] = _merge_items(old_items, candidate.get("items", []), same_event)
        for field, value in protected.items():
            current[field] = value
            stats["protected_fields"] += 1
        merged_meta = copy.deepcopy(candidate.get("field_meta", {}))
        merged_meta.update({field: old_meta[field] for field in protected})
        current["field_meta"] = merged_meta
        refs = {ref.get("source_id"): ref for ref in old_sources + candidate.get("source_refs", [])}
        current["source_refs"] = list(refs.values())
        current.pop("source_missing", None)
        stats["updated"] += 1

    if same_event:
        for i, circle in enumerate(result.get("circles", [])):
            if i not in seen_indexes and incoming.get("circles"):
                circle["source_missing"] = True
                stats["source_missing"] += 1
    else:
        result["event"] = copy.deepcopy(incoming.get("event", result["event"]))
        for circle in result.get("circles", []):
            circle["visit_status"] = "unvisited"
            for item in circle.get("items", []):
                item["purchase_state"] = "candidate"

    result["budget"] = calculate_budget(result.get("circles", []))
    result["generated_at"] = now_iso()
    return result, stats


def validate_plan(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def issue(target: list[dict[str, Any]], code: str, path: str, message: str) -> None:
        target.append({"code": code, "path": path, "message": message})

    try:
        EventPlan.model_validate(plan)
    except ValidationError as error:
        for detail in error.errors(include_url=False):
            location = ".".join(str(part) for part in detail["loc"])
            issue(errors, "schema_error", location, detail["msg"])

    if not plan.get("event", {}).get("event_id"):
        issue(errors, "missing_event_id", "event.event_id", "event_id is required")
    seen_visits: set[str] = set()
    for ci, circle in enumerate(plan.get("circles", [])):
        path = f"circles[{ci}]"
        visit_id = circle.get("visit_id")
        if not visit_id:
            issue(errors, "missing_visit_id", f"{path}.visit_id", "visit_id is required")
        elif visit_id in seen_visits:
            issue(errors, "duplicate_visit_id", f"{path}.visit_id", f"duplicate visit_id: {visit_id}")
        seen_visits.add(visit_id)
        for field, allowed in (("priority", PRIORITIES), ("visit_status", VISIT_STATUSES), ("placement_type", PLACEMENT_TYPES)):
            value = circle.get(field)
            if value not in allowed:
                issue(errors, "invalid_enum", f"{path}.{field}", f"expected one of {sorted(allowed)}, got {value!r}")
        selected_names = {str(item.get("name", "")).casefold() for item in circle.get("items", []) if item.get("purchase_state") in {"buy", "candidate"}}
        seen_items: set[str] = set()
        for ii, item in enumerate(circle.get("items", [])):
            item_path = f"{path}.items[{ii}]"
            item_id = item.get("item_id")
            if not item_id:
                issue(errors, "missing_item_id", f"{item_path}.item_id", "item_id is required")
            elif item_id in seen_items:
                issue(errors, "duplicate_item_id", f"{item_path}.item_id", f"duplicate item_id in circle: {item_id}")
            seen_items.add(item_id)
            state = item.get("purchase_state")
            if state not in PURCHASE_STATES:
                issue(errors, "invalid_enum", f"{item_path}.purchase_state", f"expected one of {sorted(PURCHASE_STATES)}, got {state!r}")
            price = item.get("price")
            if price is not None and (not isinstance(price, int) or isinstance(price, bool) or price < 0):
                issue(errors, "invalid_price", f"{item_path}.price", "price must be a non-negative integer or null")
            if price is None and state in {"buy", "candidate"}:
                issue(warnings, "unknown_price", f"{item_path}.price", "selected item has an unknown price")
            overlap = [name for name in item.get("bundle_components", []) if str(name).casefold() in selected_names]
            if state in {"buy", "candidate"} and overlap:
                issue(warnings, "possible_double_count", item_path, f"selected bundle overlaps selected items: {overlap}")
        if not circle.get("space_code"):
            issue(warnings, "unknown_space", f"{path}.space_code", "space is unknown")

    expected = calculate_budget(plan.get("circles", []))
    for key in ("planned_total", "max_total", "unknown_price_buy_count", "unknown_price_candidate_count"):
        if plan.get("budget", {}).get(key) != expected[key]:
            issue(errors, "budget_mismatch", f"budget.{key}", f"stored={plan.get('budget', {}).get(key)!r}, calculated={expected[key]!r}")
    return {"errors": errors, "warnings": warnings}
