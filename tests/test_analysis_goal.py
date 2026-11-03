"""신규 AWS/온프레미스 이전 2가지 목적의 실제 전체 보고서 회귀 검사."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analysis_goal import build_analysis_goal
from scripts.recommend_architecture import run


class AnalysisGoalTests(unittest.TestCase):
    def test_strict_two_choices_and_fail_closed_on_unknown_goal(self):
        self.assertEqual(build_analysis_goal("new_aws")["goal"], "new_aws")
        self.assertEqual(build_analysis_goal("migrate_onprem")["goal"], "migrate_onprem")
        for value in ("", None, "onprem", "production", True, "<script>"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_analysis_goal(value)

    def test_default_legacy_caller_remains_new_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            repo.mkdir()
            (repo / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
            out = Path(tmp) / "report"
            result = run(repo, out)
            self.assertEqual(result["analysis_goal"]["goal"], "new_aws")
            self.assertEqual(result["user_report"]["analysis_goal"], "new_aws")
            metadata = json.loads((out / "analysis-goal.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "reference_design_pending_review")
            self.assertFalse(metadata["deployed"])
            self.assertFalse(metadata["onprem_inventory_analyzed"])
            self.assertTrue((out / "deliverables/01-aws-to-be.svg").is_file())
            page = (out / "START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("신규 서비스 AWS 구축", page)
            self.assertNotIn("id='migration-warning'", page)
            self.assertNotIn("대안 비용·유지보수 비교 자세히", page)
            self.assertNotIn("집계 수치(운영 검증 전)", page)

    def test_onprem_intent_does_not_pretend_to_inventory_or_approve_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            repo.mkdir()
            (repo / "Dockerfile").write_text("FROM node:22\n", encoding="utf-8")
            (repo / "package.json").write_text(
                '{"dependencies":{"pg":"^8.0.0"}}', encoding="utf-8"
            )
            out = Path(tmp) / "report"
            result = run(repo, out, analysis_goal="migrate_onprem")
            self.assertEqual(result["analysis_goal"]["goal"], "migrate_onprem")
            self.assertEqual(result["user_report"]["analysis_goal"], "migrate_onprem")
            goal = json.loads((out / "analysis-goal.json").read_text(encoding="utf-8"))
            self.assertEqual(goal["status"], "onprem_inventory_and_migration_assessment_unavailable")
            for flag in ("aws_account_checked", "onprem_inventory_analyzed",
                         "migration_assessment_performed", "architecture_approved",
                         "deployed"):
                self.assertFalse(goal[flag], flag)
            self.assertFalse(result["validation"]["production_ready"])
            self.assertFalse(result["decision_record"]["approved"])
            self.assertEqual(
                json.loads((out / "artifact-index.json").read_text(encoding="utf-8"))
                ["analysis_goal"], "migrate_onprem"
            )
            page = (out / "START-HERE.html").read_text(encoding="utf-8")
            markdown = (out / "START-HERE.md").read_text(encoding="utf-8")
            recommendation = (out / "recommendation.md").read_text(encoding="utf-8")
            for text in ("온프레미스", "현황 미확인", "이전 적합성 판단 불가"):
                self.assertIn(text, page)
            self.assertIn("Rehost", page)
            self.assertIn("Replatform", page)
            self.assertIn("실제 서버", markdown)
            self.assertIn("온프레미스", recommendation)
            self.assertTrue((out / "aws-topology.svg").is_file())
            self.assertTrue((out / "deliverables/02-architecture-decisions.md").is_file())

    def test_unknown_mode_never_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            repo.mkdir()
            output = Path(tmp) / "result"
            with self.assertRaisesRegex(ValueError, "analysis_goal"):
                run(repo, output, analysis_goal="unlisted")
            self.assertFalse(output.exists())

    def test_existing_cost_report_and_patterns_unchanged_by_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "app"
            repo.mkdir()
            (repo / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")
            a = run(repo, Path(tmp) / "a", analysis_goal="new_aws")
            b = run(repo, Path(tmp) / "b", analysis_goal="migrate_onprem")
            self.assertEqual(a["option_id"], b["option_id"])
            self.assertEqual(a["aws_topology"]["pattern"], b["aws_topology"]["pattern"])
            self.assertEqual(a["cost_estimate"]["status"], "needs_input")
            self.assertEqual(b["cost_estimate"]["status"], "needs_input")
            self.assertFalse(b["user_report"]["production_ready"])


if __name__ == "__main__":
    unittest.main()
