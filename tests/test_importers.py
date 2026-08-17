import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comiket_planner.importers import import_previous


class ImporterTests(unittest.TestCase):
    def test_japanese_csv_is_normalized_for_a_new_event(self):
        fixture = Path(__file__).parent / "fixtures" / "previous.csv"
        circles = import_previous(fixture, "C110-day2")
        self.assertEqual(len(circles), 2)
        self.assertEqual(circles[0]["priority"], "A")
        self.assertEqual(circles[0]["visit_status"], "unvisited")
        self.assertEqual(circles[0]["items"][0]["price"], 1000)
        self.assertTrue(all(item["purchase_state"] == "candidate" for item in circles[0]["items"]))


if __name__ == "__main__":
    unittest.main()
