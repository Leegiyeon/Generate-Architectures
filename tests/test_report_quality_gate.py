"""User report QA: structural truthfulness and integrity, not a browser visual claim."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.recommend_architecture import run
from scripts.report_quality_gate import audit_report


def make_repo(root, *, inventory=False):
    root.mkdir()
    (root/"Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (root/"requirements.txt").write_text("fastapi==0.115.0\n", encoding="utf-8")
    if inventory:
        (root/".architecture").mkdir()
        (root/".architecture"/"onprem-inventory.json").write_text(json.dumps({
            "schema_version":"1.0",
            "servers":[
                {"id":"api01","role":"application","os":"linux",
                 "db_engine":"none","access":"internal"},
                {"id":"db01","role":"database","os":"linux",
                 "db_engine":"postgresql","access":"internal"}],
            "connections":[{"from":"api01","to":"db01","purpose":"database"}]
        }), encoding="utf-8")


class ReportQualityGateTests(unittest.TestCase):
    def test_new_aws_report_is_audited_but_visual_not_claimed(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            output=Path(temp)/"out"
            value=run(app, output, analysis_goal="new_aws")
            qa=value["report_quality"]
            self.assertEqual(qa["status"],"automated_structural_checks_passed")
            self.assertTrue(all(qa["checks"].values()))
            self.assertFalse(qa["browser_rendered"])
            self.assertFalse(qa["mobile_viewport_checked"])
            self.assertFalse(qa["manual_visual_review_completed"])
            self.assertFalse(qa["real_repository_accuracy_audited"])
            self.assertFalse(qa["aws_account_checked"])
            self.assertGreaterEqual(qa["embedded_svg_count"],1)
            self.assertEqual(qa["primary_assets_checked"],5)
            self.assertEqual(qa["supplementary_assets_checked"],0)
            self.assertEqual(qa,audit_report(output))
            self.assertEqual(json.loads((output/"report-qa.json").read_text(
                encoding="utf-8")),qa)
            html=(output/"START-HERE.html").read_text(encoding="utf-8")
            self.assertLess(html.index("id='overview'"),html.index("id='diagram'"))
            self.assertNotIn("max-height:760px",html)
            self.assertIn("미산정 · 입력 필요",html)
            self.assertIn("<details>",html)
            self.assertNotIn("입력 비용 항목·시나리오 자세히",html)

    def test_onprem_inventory_report_has_separate_svg_and_migration_review(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"repo"; make_repo(app,inventory=True)
            out=Path(temp)/"out"
            value=run(app,out,analysis_goal="migrate_onprem")
            qa=value["report_quality"]
            self.assertEqual(qa["supplementary_assets_checked"],5)
            self.assertEqual(qa["embedded_svg_count"],2)
            self.assertFalse(qa["browser_rendered"])
            html=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertLess(html.index("id='overview'"),html.index("id='onprem-as-is'"))
            self.assertLess(html.index("id='onprem-as-is'"),html.index("id='diagram'"))
            self.assertIn("Rehost / Replatform",html)
            self.assertIn("변경사항 자세히",html)
            self.assertIn("as-is-topology.svg",html)
            self.assertEqual(qa["status"],"automated_structural_checks_passed")

    def test_migrate_without_inventory_is_rejected_as_real_evidence_not_fake_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            out=Path(temp)/"out"
            run(app,out,analysis_goal="migrate_onprem")
            qa=audit_report(out)
            self.assertEqual(qa["status"],"automated_structural_checks_passed")
            html=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("id='migration-warning'",html)
            self.assertNotIn("id='onprem-as-is'",html)
            self.assertNotIn("id='migration-assessment'",html)

    def test_missing_local_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            out=Path(temp)/"out"; run(app,out)
            html=(out/"START-HERE.html")
            value=html.read_text(encoding="utf-8")
            html.write_text(value.replace("href='validation.md'",
                                          "href='missing-result.md'"),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"보고서 링크"):
                audit_report(out)

    def test_fake_navigation_anchor_and_duplicate_section_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            out=Path(temp)/"out"; run(app,out)
            file=out/"START-HERE.html"
            original=file.read_text(encoding="utf-8")
            file.write_text(original.replace("href='#overview'", "href='#invented'"),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"HTML 내부 앵커"):
                audit_report(out)
            file.write_text(original.replace("<section id='overview'",
                "<section id='diagram'"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"중복된 HTML"):
                audit_report(out)

    def test_asset_hash_and_aws_edge_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            out=Path(temp)/"out"; run(app,out)
            file=out/"deliverables/02-architecture-decisions.md"
            original=file.read_text(encoding="utf-8")
            file.write_text(original+"extra",encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"SHA-256 불일치"):
                audit_report(out)
            file.write_text(original,encoding="utf-8")
            topo=out/"aws-topology.json"
            data=json.loads(topo.read_text(encoding="utf-8"))
            data["edges"][0]["target"]="invented_nonexistent_service"
            topo.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"연결 대상 누락"):
                audit_report(out)

    def test_script_injection_and_viewbox_regressions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Path(temp)/"app"; make_repo(app)
            out=Path(temp)/"out"; run(app,out)
            page=out/"START-HERE.html"
            source=page.read_text(encoding="utf-8")
            page.write_text(source.replace("</body>","<script>alert(1)</script></body>"),
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"실행 스크립트"):
                audit_report(out)
            page.write_text(source,encoding="utf-8")
            svg=out/"aws-topology.svg"
            old=svg.read_text(encoding="utf-8")
            svg.write_text(old.replace("viewBox=", "invalid_viewBox=", 1),
                           encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"viewBox"):
                audit_report(out)


if __name__=="__main__":
    unittest.main()
