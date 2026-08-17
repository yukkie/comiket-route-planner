import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comiket_planner.core import new_plan, validate_plan
from comiket_planner.exporters import export_html


class DependencyIntegrationTests(unittest.TestCase):
    def test_pydantic_reports_structural_type_errors(self):
        plan = new_plan("event")
        plan["event"]["day"] = "not-a-number"
        report = validate_plan(plan)
        self.assertTrue(any(issue["code"] == "schema_error" for issue in report["errors"]))

    def test_jinja_escapes_title_and_embedded_json(self):
        plan = new_plan("event", "<script>alert(1)</script>")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "event.html"
            export_html(plan, output)
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)


if __name__ == "__main__":
    unittest.main()
