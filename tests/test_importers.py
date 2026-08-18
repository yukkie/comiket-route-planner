import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comiket_planner.importers import append_previous_only, enrich_with_previous, import_follow_lists, import_previous, normalize_x_handle, parse_profile_event_fields


class ImporterTests(unittest.TestCase):
    def test_profile_event_fields_clean_name_day_hall_and_space(self):
        parsed = parse_profile_event_fields("赤井ほっぺ@C108 ２日目 (日) 東２ソ-17b", "C108")
        self.assertEqual(parsed["creator_name"], "赤井ほっぺ")
        self.assertEqual(parsed["event_day"], 2)
        self.assertEqual(parsed["hall"], "東2")
        self.assertEqual(parsed["space_code"], "ソ-17b")

    def test_profile_event_fields_handle_no_side_space(self):
        parsed = parse_profile_event_fields("こまち.小丁C108日曜南A04", "C108")
        self.assertEqual(parsed["creator_name"], "こまち.小丁")
        self.assertEqual(parsed["event_day"], 2)
        self.assertEqual(parsed["space_code"], "A-04")

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

    def test_previous_import_keeps_same_handle_at_two_spaces(self):
        fixture = Path(__file__).parent / "fixtures" / "previous-two-visits.json"
        circles = import_previous(fixture, "C109")
        self.assertEqual(len(circles), 2)
        self.assertNotEqual(circles[0]["visit_id"], circles[1]["visit_id"])

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

    def test_handleless_previous_uses_unique_exact_creator_name(self):
        candidates = [{"creator_name": "Same Name", "x_handle": "new_handle", "priority": "unassigned", "genre_short": "", "event_day": None, "space_code": None, "field_meta": {}}]
        previous = [{"creator_name": "Same Name", "x_handle": None, "priority": "A", "genre_short": "本", "event_day": 2, "space_code": "A-01a", "source_refs": []}]
        enriched, stats = enrich_with_previous(candidates, previous, carry_placement=True)
        self.assertEqual(stats["matched_handles"], 1)
        self.assertEqual(enriched[0]["priority"], "A")
        self.assertEqual(enriched[0]["event_day"], 2)

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

    def test_previous_placement_is_only_carried_for_rehearsal(self):
        previous = [{
            "circle_name": "Old creator", "creator_name": "Old creator", "x_handle": "old_user",
            "priority": "B", "genre_short": "本", "space_code": "A-01a", "hall": "東1", "event_day": "2日目",
            "source_refs": [],
        }]
        circles, _ = append_previous_only([], previous, "C109", carry_placement=True)
        self.assertEqual(circles[0]["space_code"], "A-01a")
        self.assertEqual(circles[0]["hall"], "東1")
        self.assertEqual(circles[0]["event_day"], 2)

    def test_same_handle_on_two_days_remains_two_visits(self):
        previous = [
            {"circle_name": "Creator", "creator_name": "Creator", "x_handle": "same", "event_day": 1, "space_code": "a-01a", "source_refs": []},
            {"circle_name": "Creator", "creator_name": "Creator", "x_handle": "same", "event_day": 2, "space_code": "A-02b", "source_refs": []},
        ]
        circles, added = append_previous_only([], previous, "C109", carry_placement=True)
        self.assertEqual(added, 2)
        self.assertEqual({circle["event_day"] for circle in circles}, {1, 2})


if __name__ == "__main__":
    unittest.main()
