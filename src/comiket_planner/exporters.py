from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)


def export_csv(plan: dict[str, Any], output: str | Path) -> None:
    fields = ["priority", "visit_status", "space_code", "placement_type", "circle_name", "creator_name", "genre_short", "purchase", "planned_subtotal", "max_subtotal", "notes"]
    with Path(output).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for circle in plan.get("circles", []):
            chosen = [item for item in circle.get("items", []) if item.get("purchase_state") in {"buy", "candidate"}]
            writer.writerow({
                **{key: circle.get(key, "") for key in fields},
                "purchase": " / ".join(f"{item.get('name')} ({item.get('price') if item.get('price') is not None else '価格不明'}) [{item.get('purchase_state')}]" for item in chosen),
                "planned_subtotal": sum(item["price"] for item in chosen if item.get("purchase_state") == "buy" and isinstance(item.get("price"), int)),
                "max_subtotal": sum(item["price"] for item in chosen if isinstance(item.get("price"), int)),
            })


def export_html(plan: dict[str, Any], output: str | Path) -> None:
    template = _TEMPLATES.get_template("event.html.j2")
    document = template.render(
        title=str(plan.get("event", {}).get("name", "Comiket Plan")),
        plan=plan,
    )
    Path(output).write_text(document, encoding="utf-8")
