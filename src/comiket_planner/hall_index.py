from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"^\s*([ァ-ヶぁ-んA-Za-z])\s*[-－ー]?\s*(\d{1,2})", re.IGNORECASE)
AREA_RE = re.compile(r"^(東|西|南)")


def load_hall_index(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8-sig") as handle:
        index = json.load(handle)
    if not isinstance(index, dict) or not isinstance(index.get("rules"), list):
        raise ValueError("Hall index must be an object containing a rules array")
    return index


def resolve_hall(space_code: str | None, area_or_hall: str | None, index: dict[str, Any]) -> str | None:
    """Resolve a hall from an event-specific, map-derived placement index."""
    area_match = AREA_RE.match(str(area_or_hall or "").strip())
    if not space_code:
        return None
    area = area_match.group(1) if area_match else None
    match = SPACE_RE.match(unicodedata.normalize("NFKC", space_code))
    if not match:
        return None
    block = match.group(1)
    number = int(match.group(2))
    if area == "南":
        block = block.lower()
    elif area and block.isascii():
        block = block.upper()

    matches = []
    for rule in index["rules"]:
        if area and rule.get("area") != area:
            continue
        if block not in rule.get("blocks", []):
            continue
        if int(rule.get("number_min", 1)) <= number <= int(rule.get("number_max", 99)):
            matches.append(str(rule["hall"]))
    return matches[0] if len(set(matches)) == 1 else None


def apply_hall_index(circles: list[dict[str, Any]], index: dict[str, Any]) -> dict[str, int]:
    resolved = unresolved = already_exact = 0
    for circle in circles:
        current = str(circle.get("hall") or "")
        if current and not current.endswith("（番号不明）"):
            already_exact += 1
            continue
        hall = resolve_hall(circle.get("space_code"), current, index)
        if not hall:
            unresolved += 1
            continue
        circle["hall"] = hall
        circle.setdefault("field_meta", {})["hall"] = {
            "origin": "official_map_index",
            "confidence": 1.0,
            "manually_confirmed": False,
            "event_id": index.get("event_id"),
        }
        resolved += 1
    return {"resolved": resolved, "unresolved": unresolved, "already_exact": already_exact}
