import unittest
from pathlib import Path

from comiket_planner.hall_index import apply_hall_index, load_hall_index, resolve_hall


INDEX = load_hall_index(Path(__file__).parents[1] / "references" / "c108-hall-index.json")


class HallIndexTests(unittest.TestCase):
    def test_resolves_current_unknown_profiles_from_c108_map(self):
        self.assertEqual(resolve_hall("ヒ-11b", "東（番号不明）", INDEX), "東2")
        self.assertEqual(resolve_hall("タ-17b", "東（番号不明）", INDEX), "東2")
        self.assertEqual(resolve_hall("サ-58b", "東（番号不明）", INDEX), "東1")
        self.assertEqual(resolve_hall("a-18ab", "南（番号不明）", INDEX), "南2")
        self.assertEqual(resolve_hall("A-04", "南（番号不明）", INDEX), "南2")

    def test_distinguishes_japanese_a_from_latin_a(self):
        self.assertEqual(resolve_hall("ア-12a", "東（番号不明）", INDEX), "東1")
        self.assertEqual(resolve_hall("ア-80a", "東（番号不明）", INDEX), "東3")
        self.assertEqual(resolve_hall("A-12a", "東（番号不明）", INDEX), "東7")
        self.assertEqual(resolve_hall("A-33ab", None, INDEX), "東7")
        self.assertEqual(resolve_hall("a-18ab", None, INDEX), "南2")
        self.assertIsNone(resolve_hall("ア-50a", "東（番号不明）", INDEX))

    def test_only_replaces_missing_hall_number(self):
        circles = [
            {"space_code": "ヒ-11b", "hall": "東（番号不明）", "field_meta": {}},
            {"space_code": "タ-17b", "hall": "東4", "field_meta": {}},
        ]
        stats = apply_hall_index(circles, INDEX)
        self.assertEqual(circles[0]["hall"], "東2")
        self.assertEqual(circles[0]["field_meta"]["hall"]["origin"], "official_map_index")
        self.assertEqual(circles[1]["hall"], "東4")
        self.assertEqual(stats, {"resolved": 1, "unresolved": 0, "already_exact": 1})


if __name__ == "__main__":
    unittest.main()
