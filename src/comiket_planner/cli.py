from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import calculate_budget, load_json, merge_plans, new_plan, save_json, validate_plan
from .exporters import export_csv, export_html
from .importers import import_previous


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="comiket-plan", description="Build and validate a local Comiket event plan")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create an empty EventPlan")
    init.add_argument("event_id"); init.add_argument("--name"); init.add_argument("--day", type=int); init.add_argument("--output", required=True)
    previous = commands.add_parser("import-previous", help="import canonical or Japanese-column CSV/JSON")
    previous.add_argument("plan"); previous.add_argument("file"); previous.add_argument("--output")
    reconcile = commands.add_parser("reconcile", help="merge an incoming EventPlan")
    reconcile.add_argument("plan"); reconcile.add_argument("incoming"); reconcile.add_argument("--output")
    validate = commands.add_parser("validate", help="validate an EventPlan")
    validate.add_argument("plan"); validate.add_argument("--report")
    export = commands.add_parser("export", help="export an event-day view")
    export.add_argument("plan"); export.add_argument("--format", choices=("json", "csv", "html"), required=True); export.add_argument("--output", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "init":
        save_json(args.output, new_plan(args.event_id, args.name, args.day)); print(f"created {args.output}"); return 0
    if args.command == "import-previous":
        plan = load_json(args.plan); incoming = {"event": plan["event"], "circles": import_previous(args.file, plan["event"]["event_id"])}
        merged, stats = merge_plans(plan, incoming); output = args.output or args.plan; save_json(output, merged); print(json.dumps(stats, ensure_ascii=False)); return 0
    if args.command == "reconcile":
        merged, stats = merge_plans(load_json(args.plan), load_json(args.incoming)); output = args.output or args.plan; save_json(output, merged); print(json.dumps(stats, ensure_ascii=False)); return 0
    if args.command == "validate":
        report = validate_plan(load_json(args.plan)); rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report: Path(args.report).write_text(rendered + "\n", encoding="utf-8")
        print(rendered); return 1 if report["errors"] else 0
    plan = load_json(args.plan); plan["budget"] = calculate_budget(plan.get("circles", []))
    if args.format == "json": save_json(args.output, plan)
    elif args.format == "csv": export_csv(plan, args.output)
    else: export_html(plan, args.output)
    print(f"exported {args.output}"); return 0


if __name__ == "__main__":
    sys.exit(main())
