import tempfile
import unittest
from pathlib import Path
from scripts.recommend_architecture import scan, design

class ArchitectureTests(unittest.TestCase):
    def test_web_detects_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "package.json").write_text("{}")
            Path(tmp, "next.config.js").write_text("")
            result = design(scan(Path(tmp)), "auto", None)
            self.assertEqual(result["workload"], "web")
            self.assertIn("CloudFront", result["nodes"])

    def test_mobile_detects_expo(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "app.json").write_text("{}")
            result = design(scan(Path(tmp)), "auto", 200)
            self.assertEqual(result["workload"], "mobile")
            self.assertEqual(result["input_budget_usd_month"], 200)

    def test_empty_repo_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = design(scan(Path(tmp)), "auto", None)
            self.assertTrue(result["nodes"])

if __name__ == "__main__":
    unittest.main()
