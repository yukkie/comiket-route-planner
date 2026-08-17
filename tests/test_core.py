import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comiket_planner.core import calculate_budget, merge_plans, new_plan, validate_plan


def circle(name="A", visit_id="v1"):
    return {"visit_id": visit_id, "circle_name": name, "creator_name": None, "aliases": [], "x_user_id": None, "x_handle": None, "space_code": "東A01a", "hall": "東1", "placement_type": "wall", "priority": "A", "genre_short": "創作", "visit_status": "purchased", "notes": "keep", "items": [{"item_id": "i1", "name": "新刊", "price": 1000, "currency": "JPY", "purchase_state": "buy", "availability": "unknown", "age_rating": "all", "bundle_components": [], "source_refs": []}], "field_meta": {field: {"origin": "user", "manually_confirmed": True} for field in ("priority", "genre_short", "visit_status", "notes")}, "source_refs": []}


class CoreTests(unittest.TestCase):
    def test_budget_keeps_unknown_separate(self):
        c = circle(); c["items"].append({"item_id": "i2", "name": "グッズ", "price": None, "purchase_state": "candidate", "bundle_components": []})
        budget = calculate_budget([c])
        self.assertEqual((budget["planned_total"], budget["max_total"]), (1000, 1000))
        self.assertEqual(budget["unknown_price_candidate_count"], 1)

    def test_same_event_protects_manual_fields_and_item_choice(self):
        base = new_plan("C110-day1"); base["circles"] = [circle()]
        incoming = new_plan("C110-day1"); changed = circle(); changed.update(priority="C", genre_short="changed", visit_status="unvisited", notes="changed"); changed["items"][0]["purchase_state"] = "skip"; incoming["circles"] = [changed]
        merged, stats = merge_plans(base, incoming)
        actual = merged["circles"][0]
        self.assertEqual((actual["priority"], actual["genre_short"], actual["visit_status"], actual["notes"]), ("A", "創作", "purchased", "keep"))
        self.assertEqual(actual["items"][0]["purchase_state"], "buy")
        self.assertEqual(stats["protected_fields"], 4)

    def test_new_event_resets_progress_to_candidates(self):
        base = new_plan("old"); base["circles"] = [circle()]
        incoming = new_plan("new"); incoming["circles"] = [circle()]
        merged, _ = merge_plans(base, incoming)
        self.assertEqual(merged["circles"][0]["visit_status"], "unvisited")
        self.assertEqual(merged["circles"][0]["items"][0]["purchase_state"], "candidate")

    def test_name_match_prevents_duplicate_when_ids_change(self):
        base = new_plan("event"); base["circles"] = [circle(visit_id="old-id")]
        incoming = new_plan("event"); incoming["circles"] = [circle(visit_id="new-id")]
        merged, stats = merge_plans(base, incoming)
        self.assertEqual(len(merged["circles"]), 1)
        self.assertEqual(stats["updated"], 1)

    def test_validator_detects_budget_mismatch(self):
        plan = new_plan("event"); plan["circles"] = [circle()]
        report = validate_plan(plan)
        self.assertTrue(any(i["code"] == "budget_mismatch" for i in report["errors"]))


if __name__ == "__main__":
    unittest.main()
