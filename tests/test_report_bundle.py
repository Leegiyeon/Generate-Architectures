"""Issue #14: 사용자용 한 장 보고서·4개 주요 산출물·미검증 상태 일관성."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.recommend_architecture import run
from scripts.report_bundle import generate_user_bundle


class ReportLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.scripts = 0
    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts += 1
        for k, v in attrs:
            if k == "href":
                self.hrefs.append(v)


def example_project(root, option="containers", requirements=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "static": {"vite.config.ts": "export default {}"},
        "serverless": {"pyproject.toml": "[project]\nname='api'\n"},
        "mobile": {"app.json": "{}"},
        "containers": {"Dockerfile": "FROM python:3.12"},
    }
    for name, value in files[option].items():
        (root/name).write_text(value, encoding="utf-8")
    if requirements:
        (root/"req.json").write_text(json.dumps(requirements), encoding="utf-8")
    return "req.json" if requirements else None


class UserReportTests(unittest.TestCase):
    def test_one_click_self_contained_html_and_primary_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/"project"
            req = example_project(root, requirements={"peak_rps":240,
                                                       "latency_target_ms":500,
                                                       "requires_authentication":True})
            out = Path(tmp)/"output"
            result=run(root,out,requirements_file=req)
            self.assertIn("user_report", result)
            self.assertEqual(result["user_report"]["entrypoint"],"START-HERE.html")
            report=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy",report)
            self.assertIn("default-src &#x27;none&#x27;",report)
            self.assertIn("data:image/svg+xml;base64,",report)
            for label in ("① AWS To-Be","② 서비스 선정","③ 보안","④ 비용",
                          "As-Is", "To-Be","Run workflow","검증"):
                self.assertIn(label,report)
            parser=ReportLinks()
            parser.feed(report)
            self.assertEqual(parser.scripts,0)
            for ref in parser.hrefs:
                self.assertFalse(ref.startswith(("http:","https:","javascript:")),ref)
                if not ref.startswith("#"):
                    self.assertTrue((out/ref).is_file(),ref)
            self.assertIn("아키텍처", (out/"START-HERE.md").read_text(encoding="utf-8"))
            self.assertIn("START-HERE.html",
                          (out/"recommendation.md").read_text(encoding="utf-8"))
            self.assertTrue((out/"architecture.svg").is_file())
            self.assertTrue((out/"application-graph.svg").is_file())

    def test_manifest_has_stable_four_deliverable_categories_and_matching_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            example_project(root)
            out=Path(tmp)/"out"
            result=run(root,out)
            manifest=json.loads((out/"artifact-index.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["aws_account_checked"])
            self.assertFalse(manifest["production_ready"])
            self.assertEqual(manifest["chosen_option"],result["option_id"])
            self.assertEqual(manifest["reference_nodes"],result["aws_topology"]["nodes"])
            self.assertEqual({x["kind"] for x in manifest["primary_files"]},
                             {"diagram","decision","operations","cost"})
            self.assertEqual(len(manifest["primary_files"]),5)
            for row in manifest["primary_files"]:
                content=(out/row["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(),row["sha256"])
            self.assertEqual((out/"deliverables/01-aws-to-be.svg").read_bytes(),
                             (out/"aws-topology.svg").read_bytes())
            self.assertEqual((out/"deliverables/01-aws-to-be.png").read_bytes(),
                             (out/"aws-topology.png").read_bytes())
            self.assertIn("상세 논리도",manifest["primary_files"][0]["description"])
            self.assertIn("서비스 선정", (out/"deliverables/02-architecture-decisions.md").read_text(encoding="utf-8"))
            self.assertIn("RTO", (out/"deliverables/03-security-operations.md").read_text(encoding="utf-8"))

    def test_unpriced_cost_stays_unpriced_and_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            req=example_project(root,"static")
            out=Path(tmp)/"out"
            run(root,out,requirements_file=req)
            cost=(out/"deliverables/04-cost-capacity.md").read_text(encoding="utf-8")
            html=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("미산정",cost)
            self.assertIn("미산정",html)
            self.assertNotIn("0 USD",cost)
            self.assertIn("CloudFront",html)
            manifest=json.loads((out/"artifact-index.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["cost_status"],"needs_input")

    def test_partial_cost_only_displays_subtotal_not_full_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            example_project(root,"containers")
            (root/"cost.json").write_text(json.dumps({
                "region":"ap-northeast-2",
                "items":[
                    {"id":"ingress","unit":"Hrs","quantity":100,
                     "rate":{"kind":"manual_quote","unit_price_usd":0.25,
                             "source":"https://aws.amazon.com/pricing/",
                             "as_of":"2026-11-03"}},
                    {"id":"outbound","unit":"GB","quantity":10,
                     "rate":{"kind":"unknown"}},
                ],
            }),encoding="utf-8")
            out=Path(tmp)/"out"
            run(root,out,cost_input="cost.json")
            report=(out/"deliverables/04-cost-capacity.md").read_text(encoding="utf-8")
            self.assertIn("25.00 USD",report)
            self.assertIn("부분합",report)
            self.assertIn("총액 아님",report)
            index=json.loads((out/"artifact-index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["cost_status"],"partial_unpriced")
            self.assertTrue(index["cost_total_only_covers_user_input"])

    def test_all_four_patterns_have_no_fake_approval_or_missing_assets(self):
        for scenario in ("static","serverless","mobile","containers"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/"repo"
                example_project(root,scenario)
                out=Path(tmp)/"out"
                result=run(root,out)
                page=(out/"START-HERE.html").read_text(encoding="utf-8")
                self.assertIn("승인 전",page)
                self.assertIn("AWS 계정",page)
                self.assertFalse(result["user_report"]["production_ready"])
                self.assertFalse(result["validation"]["production_ready"])
                self.assertTrue((out/"deliverables/01-aws-to-be.svg").is_file())

    def test_escaped_user_visible_text_cannot_inject_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            example_project(root)
            out=Path(tmp)/"out"
            result=run(root,out)
            def doc(name):
                return json.loads((out/name).read_text(encoding="utf-8"))
            malicious="<script>alert('x')</script>"
            result["pattern"]=malicious
            profile=doc("evidence-contract.json")
            matrix=doc("architecture-decision-matrix.json")
            adr=doc("decision-record.json")
            topology=doc("aws-topology.json")
            ops=doc("security-operations.json")
            cost=doc("cost-estimate.json")
            validation=doc("validation.json")
            generate_user_bundle(out,result,topology,doc("application-graph.json"),
                                 profile,matrix,adr,ops,cost,validation)
            page=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertNotIn(malicious,page)
            self.assertIn("&lt;script&gt;",page)
            parsed=ReportLinks()
            parsed.feed(page)
            self.assertEqual(parsed.scripts,0)

    def test_inconsistent_gateway_cannot_create_misleading_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            example_project(root)
            out=Path(tmp)/"out"
            result=run(root,out)
            def doc(name):
                return json.loads((out/name).read_text(encoding="utf-8"))
            topology=doc("aws-topology.json")
            topology["status"]="production_ready"
            with self.assertRaisesRegex(ValueError,"일관성"):
                generate_user_bundle(
                    out,result,topology,doc("application-graph.json"),
                    doc("evidence-contract.json"),doc("architecture-decision-matrix.json"),
                    doc("decision-record.json"),doc("security-operations.json"),
                    doc("cost-estimate.json"),doc("validation.json"))


if __name__ == "__main__":
    unittest.main()
