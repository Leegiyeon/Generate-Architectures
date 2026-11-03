"""Issue #15: ECS/EC2/Lambda 동일 월 업무량 사용자 입력 비용/운영책임 비교 테스트.

가격은 테스트용 가상 단가일 뿐 실제 AWS 제공 가격이 아닙니다.
"""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.alternative_cost_comparison import (
    compare_alternatives, markdown_comparison, read_alternative_cost_input,
    validate_alternative_cost_input,
)
from scripts.recommend_architecture import run


def priced_item(ident, service, minimum=50, baseline=100, peak=200, rate="0.20",
                unit="Hrs"):
    return {
        "id": ident, "service": service, "unit": unit,
        "quantities": {"minimum": minimum, "baseline": baseline, "peak": peak},
        "rate": {"kind": "manual_quote", "unit_price_usd": rate,
                 "source": "https://aws.amazon.com/pricing/",
                 "as_of": "2026-11-03"},
    }


def input_file(*, with_shared=True, three=False, unpriced=False):
    shared = [
        priced_item("data_transfer", "data_transfer", minimum=4,
                    baseline=10, peak=20, rate="0.5", unit="GB"),
        priced_item("logs", "cloudwatch_logs", minimum=1,
                    baseline=1, peak=2, rate="1", unit="GB"),
    ] if with_shared else []
    fargate = [
        priced_item("fargate_alb", "alb"),
        priced_item("fargate_cpu", "ecs_fargate", rate="0.3",
                    unit="vCPU-Hours"),
    ]
    ec2 = [
        priced_item("ec2_alb", "alb"),
        priced_item("ec2_inst", "ec2", rate="0.1"),
    ]
    if unpriced:
        ec2[1]["rate"] = {"kind": "unknown"}
    candidates = [
        {"id": "fargate", "items": fargate},
        {"id": "ec2", "items": ec2},
    ]
    if three:
        candidates.append({"id": "lambda", "items": [
            priced_item("lambda_request", "lambda",
                        40000, 100000, 200000, rate="0.000002", unit="Requests"),
            priced_item("lambda_api", "api_gateway",
                        40000, 100000, 200000, rate="0.000004", unit="Requests"),
        ]})
    return {
        "schema_version": "1.0", "region": "ap-northeast-2",
        "workload": {
            "id": "web_api", "monthly_requests": {
                "minimum": 40000, "baseline": 100000, "peak": 200000
            }, "peak_rps": 50,
        },
        "shared_items": shared, "candidates": candidates,
    }


def matrix(blocked=None):
    return {"candidates": [{"id": ident,
                            "blockers": [{"rule_id": "HOST-001", "reason": "호스트 제어 필요"}]
                                        if ident == blocked else []}
                           for ident in ("fargate", "ec2", "lambda")]}


REQ = {"region": "ap-northeast-2",
       "expected_monthly_requests": 100000, "peak_rps": 50}


class AWSAlternativeCostTests(unittest.TestCase):
    def test_identical_workload_shared_items_and_modeled_delta_not_recommendation(self):
        report = compare_alternatives(input_file(), REQ, matrix())
        self.assertEqual(report["status"], "modeled_items_comparable_unverified")
        self.assertTrue(report["requirements_matched"])
        self.assertIsNone(report["recommended_by_cost"])
        self.assertFalse(report["auto_selected"])
        self.assertFalse(report["capacity_benchmarked"])
        self.assertFalse(report["production_ready"])
        self.assertEqual([c["id"] for c in report["candidates"]], ["fargate", "ec2"])
        by_id = {c["id"]: c for c in report["candidates"]}
        self.assertEqual(by_id["fargate"]["scenarios"]["baseline"]
                         ["provided_items_total_usd"], "56.00")
        self.assertEqual(by_id["ec2"]["scenarios"]["baseline"]
                         ["provided_items_total_usd"], "36.00")
        self.assertEqual(report["comparisons"][1]["deltas_from_minimum_modeled_usd"],
                         {"fargate": "20.00", "ec2": "0.00"})
        self.assertIn("OS·AMI·패치", markdown_comparison(report))
        self.assertIn("사용자 입력 비용", markdown_comparison(report))
        self.assertTrue(all(not x["approved"] for x in report["candidates"]))

    def test_three_candidates_share_same_monthly_api_workload_without_auto_choice(self):
        report=compare_alternatives(input_file(three=True),REQ,matrix())
        self.assertEqual(report["status"], "modeled_items_comparable_unverified")
        self.assertEqual([c["id"] for c in report["candidates"]],
                         ["fargate", "ec2", "lambda"])
        self.assertEqual(len(report["comparisons"]),3)
        self.assertTrue(all(c["monthly_requests"]["baseline"]==100000
                            for c in report["candidates"]))
        self.assertIn("동시성",report["candidates"][2]["operational_responsibilities"]["platform"])
        self.assertIsNone(report["recommended_by_cost"])

    def test_unknown_sku_disables_modeled_delta_and_zero_fill(self):
        report = compare_alternatives(input_file(unpriced=True), REQ, matrix())
        self.assertEqual(report["status"], "partial_unpriced")
        self.assertFalse(report["comparisons"])
        ec2 = next(c for c in report["candidates"] if c["id"]=="ec2")
        self.assertIsNone(ec2["scenarios"]["baseline"]["provided_items_total_usd"])
        self.assertEqual(ec2["scenarios"]["baseline"]["unpriced_items"],1)
        self.assertEqual(ec2["scenarios"]["baseline"]["priced_subtotal_usd"],"26.00")
        self.assertNotIn("월 전체 예상", markdown_comparison(report))

    def test_missing_shared_costs_disables_comparison(self):
        report = compare_alternatives(input_file(with_shared=False),REQ,matrix())
        self.assertEqual(report["status"],"missing_service_cost_categories")
        self.assertFalse(report["comparisons"])
        self.assertEqual(report["candidates"][0]["missing_categories"],
                         ["cloudwatch_logs", "data_transfer"])
        self.assertEqual(report["candidates"][0]["scenarios"]["baseline"]
                         ["provided_items_total_usd"], "50.00")

    def test_template_blockers_prevent_cost_ranking(self):
        report=compare_alternatives(input_file(three=True),REQ,matrix(blocked="lambda"))
        self.assertEqual(report["status"],"blocked_by_constraints")
        self.assertFalse(report["comparisons"])
        self.assertEqual(report["candidates"][2]["status"],
                         "blocked_for_current_template")

    def test_mismatched_region_request_count_or_peak_rps_disables_comparison(self):
        for req in (
            {**REQ, "region": "us-east-1"},
            {**REQ, "expected_monthly_requests": 99999},
            {**REQ, "peak_rps": 100},
        ):
            with self.subTest(req=req):
                report=compare_alternatives(input_file(),req,matrix())
                self.assertEqual(report["status"],"requirements_mismatch")
                self.assertFalse(report["comparisons"])
                self.assertFalse(report["requirements_matched"])

    def test_strict_schema_and_duplicate_or_unsafe_quantities(self):
        original=input_file()
        cases=[]
        cases.append({**original,"workload":{**original["workload"],
                      "monthly_requests":{"minimum":1,"baseline":2}}})
        cases.append({**original,"workload":{**original["workload"],
                      "peak_rps":True}})
        cases.append({**original,"workload":{**original["workload"],
                      "peak_rps":float("nan")}})
        cases.append({**original,"workload":{**original["workload"],
                      "monthly_requests":{"minimum":40000,"baseline":100000,
                                          "peak":90000}}})
        cases.append({**original,"candidates":[original["candidates"][0],
                                             original["candidates"][0]]})
        cases.append({**original,"candidates":[
            original["candidates"][0],{"id":"static","items":original["candidates"][1]["items"]}]})
        cases.append({**original,"shared_items":[original["shared_items"][0]]*2})
        bad=dict(original["candidates"][0]["items"][0])
        bad["rate"]={"kind":"manual_quote", "unit_price_usd":0.2,
                     "source":"https://evil.example.com/pricing","as_of":"2026-11-03"}
        cases.append({**original,"candidates":[
            {"id":"fargate","items":[bad]+original["candidates"][0]["items"][1:]},
            original["candidates"][1]]})
        for value in cases:
            with self.subTest(value=str(value)[:80]):
                with self.assertRaises(ValueError):
                    validate_alternative_cost_input(value)

    def test_no_input_is_explicit_without_false_zero_or_hidden_cost(self):
        result=compare_alternatives(None,REQ,matrix())
        self.assertEqual(result["status"],"needs_input")
        self.assertFalse(result["candidates"])
        self.assertFalse(result["auto_selected"])
        self.assertIn("입력 대기",markdown_comparison(result))
        self.assertNotIn("0 USD",markdown_comparison(result))

    def test_input_file_restricts_path_symlink_and_file_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"comparison.json").write_text(json.dumps(input_file()),encoding="utf-8")
            validated=read_alternative_cost_input(root,"comparison.json")
            self.assertEqual(validated["workload"]["id"],"web_api")
            with self.assertRaises(ValueError):
                read_alternative_cost_input(root,"../secret.json")
            (root/"alias.json").symlink_to(root/"comparison.json")
            with self.assertRaises(ValueError):
                read_alternative_cost_input(root,"alias.json")
            (root/"oversized.json").write_text(" "*65537)
            with self.assertRaises(ValueError):
                read_alternative_cost_input(root,"oversized.json")

    def test_full_pipeline_links_same_workload_comparison_without_changing_adr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"requirements.json").write_text(json.dumps(REQ),encoding="utf-8")
            (root/"comparison.json").write_text(json.dumps(input_file()),encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,requirements_file="requirements.json",
                       alternative_cost_input="comparison.json")
            self.assertEqual(result["option_id"],"containers")
            self.assertEqual(result["alternative_cost_comparison"]["status"],
                             "modeled_items_comparable_unverified")
            self.assertFalse(result["decision_record"]["approved"])
            self.assertEqual(result["cost_estimate"]["status"],"needs_input")
            doc=json.loads((out/"alternative-cost-comparison.json")
                           .read_text(encoding="utf-8"))
            self.assertIsNone(doc["recommended_by_cost"])
            self.assertEqual(doc["comparisons"][1]["deltas_from_minimum_modeled_usd"]
                             ["fargate"],"20.00")
            html=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("동일 업무량",html)
            self.assertIn("alternative-cost-comparison.md",html)
            self.assertIn("ECS/EC2/Lambda", (out/"START-HERE.md").read_text(encoding="utf-8"))
            self.assertIn("동일 업무량", (out/"deliverables/04-cost-capacity.md")
                          .read_text(encoding="utf-8"))
            self.assertIn("18. 동일 업무량", (out/"recommendation.md").read_text(encoding="utf-8"))
            self.assertTrue((out/"architecture.svg").is_file())


if __name__=="__main__":
    unittest.main()
