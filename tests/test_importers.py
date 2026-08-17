import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comiket_planner.importers import append_previous_only, enrich_with_previous, import_follow_lists, import_previous, normalize_x_handle


class ImporterTests(unittest.TestCase):
    def test_normalize_x_handle_accepts_urls_and_mentions(self):
        self.assertEqual(normalize_x_handle("https://x.com/Example_1"), "Example_1")
        self.assertEqual(normalize_x_handle("@Example_1 / @second"), "Example_1")

    def test_japanese_csv_is_normalized_for_a_new_event(self):
        fixture = Path(__file__).parent / "fixtures" / "previous.csv"
        circles = import_previous(fixture, "C110-day2")
        self.assertEqual(len(circles), 2)
        self.assertEqual(circles[0]["priority"], "A")
        self.assertEqual(circles[0]["visit_status"], "unvisited")
        self.assertEqual(circles[0]["items"][0]["price"], 1000)
        self.assertTrue(all(item["purchase_state"] == "candidate" for item in circles[0]["items"]))

    def test_follow_lists_merge_by_handle_and_keep_sources(self):
        fixture_dir = Path(__file__).parent / "fixtures"
        circles, stats = import_follow_lists(
            [fixture_dir / "follow-general.json", fixture_dir / "follow-adult.json"],
            "C109",
        )
        self.assertEqual(stats["input_records"], 3)
        self.assertEqual(stats["unique_handles"], 2)
        repeated = next(circle for circle in circles if circle["x_handle"].casefold() == "same_user")
        self.assertEqual(len(repeated["source_refs"]), 2)
        self.assertFalse(repeated["circle_name_confirmed"])

    def test_previous_priority_and_genre_enrich_matching_handle_only(self):
        candidates = [{"x_handle": "same_user", "priority": "unassigned", "genre_short": "", "field_meta": {}}]
        previous = [
            {"x_handle": "SAME_USER", "priority": "A", "genre_short": "男の娘", "source_refs": []},
            {"x_handle": "missing", "priority": "B", "genre_short": "本", "source_refs": []},
        ]
        enriched, stats = enrich_with_previous(candidates, previous)
        self.assertEqual(enriched[0]["priority"], "A")
        self.assertEqual(enriched[0]["genre_short"], "男の娘")
        self.assertEqual(stats["matched_handles"], 1)
        self.assertEqual(len(stats["unmatched_previous"]), 1)

    def test_previous_only_entry_is_reset_for_new_event(self):
        previous = [{
            "circle_name": "Old creator", "creator_name": "Old creator", "x_handle": "old_user",
            "priority": "B", "genre_short": "本", "space_code": "A-01a", "visit_status": "purchased",
            "source_refs": [],
        }]
        circles, added = append_previous_only([], previous, "C109")
        self.assertEqual(added, 1)
        self.assertIsNone(circles[0]["space_code"])
        self.assertEqual(circles[0]["visit_status"], "unvisited")
        self.assertEqual(circles[0]["priority"], "B")


if __name__ == "__main__":
    unittest.main()
