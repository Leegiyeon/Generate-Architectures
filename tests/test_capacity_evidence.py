"""Issue #15: 안전한 집계 부하 테스트 제출·용량 가정·비용 비교 차단 테스트.

수치는 사용자/테스트용 합성 예시이며 실제 AWS에서 측정한 값이 아닙니다.
"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from scripts.capacity_evidence import (
    analyze_capacity_evidence, markdown_capacity, read_capacity_evidence,
    validate_capacity_evidence,
)
from scripts.recommend_architecture import run


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/capacity-evidence.example.json"
ALTERNATIVE_EXAMPLE = Path(__file__).resolve().parents[1] / "examples/alternative-cost-comparison.example.json"
REQ = {"region": "ap-northeast-2", "peak_rps": 100, "latency_target_ms": 250,
       "expected_monthly_requests": 100000}


def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def alternative_sample():
    return json.loads(ALTERNATIVE_EXAMPLE.read_text(encoding="utf-8"))


def expected_candidates():
    return [{"id":name} for name in ("fargate","ec2","lambda")]


def alt_contract():
    return {"region": "ap-northeast-2", "workload": {
        "id": "api_example", "peak_rps": 100,
    }, "candidates": expected_candidates()}


class CapacityEvidenceTests(unittest.TestCase):
    def test_all_three_example_runs_meet_user_test_thresholds_but_not_prod_certified(self):
        doc=sample()
        report=analyze_capacity_evidence(doc,REQ,alt_contract())
        self.assertEqual(report["status"],"observed_targets_met_limited")
        self.assertTrue(report["all_observed_targets_met"])
        self.assertTrue(report["requirements_matched"])
        self.assertFalse(report["evidence_authenticity_verified"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["autoscaling_verified"])
        self.assertFalse(report["aws_quotas_verified"])
        self.assertFalse(report["cost_adjustment_automated"])
        self.assertEqual(len(report["results"]),3)
        self.assertFalse(report["results"][0]["observed"]["scale_out_observed"])
        self.assertIsNone(report["results"][0]["planning_only"])
        self.assertEqual(report["results"][2]["planning_only"]["suggested_count"],18)
        self.assertEqual(report["results"][2]["planning_only"]["unit"],
                         "approximate_mean_concurrent_executions")
        self.assertIn("쿼터",markdown_capacity(report))

    def test_evidence_rps_below_target_is_not_capacity_success(self):
        doc=sample()
        doc["results"][0]["sustained_rps"]=70
        report=analyze_capacity_evidence(doc,REQ,alt_contract())
        self.assertEqual(report["status"],"observed_targets_not_met")
        self.assertFalse(report["all_observed_targets_met"])
        self.assertFalse(report["results"][0]["meets_user_supplied_test_thresholds"]["sustained_rps"])

    def test_p95_errors_and_min_duration_are_independent_user_thresholds(self):
        for field,value,flag in (
            ("p95_latency_ms",300,"p95_latency_ms"),
            ("error_rate_percent",3,"error_rate_percent"),
            ("duration_seconds",10,"duration_seconds"),
        ):
            with self.subTest(field=field):
                doc=sample()
                doc["results"][1][field]=value
                report=analyze_capacity_evidence(doc,REQ,alt_contract())
                self.assertEqual(report["status"],"observed_targets_not_met")
                self.assertFalse(report["results"][1]["meets_user_supplied_test_thresholds"][flag])

    def test_missing_candidate_prevents_global_pass_without_inventing_zero(self):
        doc=sample()
        doc["results"]=doc["results"][:-1]
        report=analyze_capacity_evidence(doc,REQ,alt_contract())
        self.assertEqual(report["status"],"benchmark_candidates_incomplete")
        self.assertFalse(report["all_observed_targets_met"])
        self.assertEqual(report["expected_candidates"],["ec2","fargate","lambda"])

    def test_mismatched_workload_and_region_or_latency_block_evidence(self):
        for key, value in (("peak_rps",99),("latency_target_ms",200),
                           ("region","us-east-1")):
            with self.subTest(key=key):
                report=analyze_capacity_evidence(sample(),{**REQ,key:value},alt_contract())
                self.assertEqual(report["status"],"requirements_mismatch")
                self.assertFalse(report["all_observed_targets_met"])
        doc=sample()
        doc["workload_id"]="another_app"
        report=analyze_capacity_evidence(doc,REQ,alt_contract())
        self.assertEqual(report["status"],"requirements_mismatch")

    def test_linear_extrapolation_must_be_explicit_and_is_not_recommendation(self):
        doc=sample()
        doc["allow_linear_extrapolation"]=True
        doc["results"][0]["sustained_rps"]=70
        doc["targets"]["peak_rps"]=150
        req={**REQ, "peak_rps":150}
        alt=alt_contract()
        alt["workload"]["peak_rps"]=150
        report=analyze_capacity_evidence(doc,req,alt)
        calculated=report["results"][0]["planning_only"]
        self.assertEqual(calculated["suggested_count"],5) # ceil(150 * 2 / 70)
        self.assertEqual(calculated["unit"],"ecs_tasks")
        self.assertIn("unverified_linear",calculated["status"])
        self.assertFalse(report["all_observed_targets_met"])
        self.assertFalse(report["cost_adjustment_automated"])

    def test_lambda_uses_average_duration_not_p95_for_theoretical_concurrency(self):
        doc=sample()
        doc["results"][2]["p95_latency_ms"]=250
        doc["results"][2]["avg_duration_ms"]=180
        report=analyze_capacity_evidence(doc,REQ,alt_contract())
        self.assertEqual(report["results"][2]["planning_only"]["suggested_count"],18)
        self.assertIn("observed_mean_duration",report["results"][2]["planning_only"]["formula"])
        self.assertFalse(report["results"][2]["quota_checked"])

    def test_refuses_secrets_raw_logs_nan_duplicate_invalid_date_and_negative_values(self):
        base=sample()
        invalid=[]
        invalid.append({**base,"api_url":"https://somewhere.example.com/private"})
        invalid.append({**base,"tested_on":"2026-02-30"})
        invalid.append({**base,"region":"http://private"})
        invalid.append({**base,"benchmark_id":"<script>alert(1)</script>"})
        invalid.append({**base,"allow_linear_extrapolation":1})
        invalid.append({**base,"targets":{**base["targets"],"peak_rps":float("nan")}})
        invalid.append({**base,"targets":{**base["targets"],"max_error_rate_percent":120}})
        invalid.append({**base,"results":base["results"]+base["results"][:1]})
        for key,value in (
            ("sustained_rps",float("inf")),
            ("p95_latency_ms",-1),
            ("error_rate_percent",101),
            ("duration_seconds",0),
            ("observed_capacity_units",2.5),
            ("scale_out_observed","true"),
        ):
            copy=deepcopy(base)
            copy["results"][0][key]=value
            invalid.append(copy)
        copy=deepcopy(base)
        copy["results"][2]["avg_duration_ms"]=None
        invalid.append(copy)
        copy=deepcopy(base)
        copy["results"][0]["avg_duration_ms"]=180
        invalid.append(copy)
        copy=deepcopy(base)
        copy["results"][0]["raw_log"]="SECRET"
        invalid.append(copy)
        for bad in invalid:
            with self.subTest(reason=str(bad)[:85]):
                with self.assertRaises(ValueError):
                    validate_capacity_evidence(bad)

    def test_input_path_rejects_symlink_traversal_and_oversize_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"cap.json").write_text(json.dumps(sample()),encoding="utf-8")
            self.assertEqual(read_capacity_evidence(root,"cap.json")["benchmark_id"],
                             "synthetic-api-20261103")
            with self.assertRaises(ValueError):
                read_capacity_evidence(root,"../outside.json")
            (root/"link.json").symlink_to(root/"cap.json")
            with self.assertRaises(ValueError):
                read_capacity_evidence(root,"link.json")
            (root/"big.json").write_text(" "*32769,encoding="utf-8")
            with self.assertRaises(ValueError):
                read_capacity_evidence(root,"big.json")

    def test_input_missing_outputs_unverified_not_zero(self):
        report=analyze_capacity_evidence(None,REQ,None)
        self.assertEqual(report["status"],"needs_input")
        self.assertFalse(report["all_observed_targets_met"])
        self.assertFalse(report["production_ready"])
        self.assertNotIn("0 AWS",markdown_capacity(report))

    def test_full_pipeline_report_block_scenario_and_no_automated_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"requirements.json").write_text(json.dumps(REQ),encoding="utf-8")
            alt=alternative_sample()
            for candidate in alt["candidates"]:
                for item in candidate["items"]:
                    item["rate"]={"kind":"manual_quote","unit_price_usd":"0.10",
                                  "source":"https://aws.amazon.com/pricing/",
                                  "as_of":"2026-11-03"}
            for item in alt["shared_items"]:
                item["rate"]={"kind":"manual_quote","unit_price_usd":"0.10",
                              "source":"https://aws.amazon.com/pricing/",
                              "as_of":"2026-11-03"}
            (root/"alt.json").write_text(json.dumps(alt),encoding="utf-8")
            cap=sample()
            cap["results"][2]["sustained_rps"]=40
            (root/"cap.json").write_text(json.dumps(cap),encoding="utf-8")
            out=Path(tmp)/"output"
            result=run(root,out,requirements_file="requirements.json",
                       alternative_cost_input="alt.json", capacity_evidence="cap.json")
            self.assertEqual(result["capacity_evidence"]["status"],
                             "observed_targets_not_met")
            self.assertFalse(result["capacity_evidence"]["production_ready"])
            self.assertEqual(result["alternative_cost_comparison"]["status"],
                             "capacity_evidence_review_required")
            cost=json.loads((out/"alternative-cost-comparison.json")
                            .read_text(encoding="utf-8"))
            self.assertFalse(cost["comparisons"])
            self.assertTrue(cost["capacity_evidence_supplied"])
            self.assertIsNone(cost["recommended_by_cost"])
            self.assertFalse(result["decision_record"]["approved"])
            self.assertEqual(result["option_id"],"containers")
            page=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("집계 수치",page)
            self.assertIn("capacity-evidence.md",page)
            self.assertIn("부하 테스트", (out/"deliverables/04-cost-capacity.md")
                          .read_text(encoding="utf-8"))
            self.assertIn("19. 입력된 부하 시험", (out/"recommendation.md")
                          .read_text(encoding="utf-8"))
            self.assertTrue((out/"aws-topology.svg").is_file())

    def test_passed_user_test_values_still_not_production_certification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"cap.json").write_text(json.dumps(sample()),encoding="utf-8")
            (root/"requirements.json").write_text(json.dumps(REQ),encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,requirements_file="requirements.json",
                       capacity_evidence="cap.json")
            self.assertTrue(result["capacity_evidence"]["all_observed_targets_met"])
            self.assertFalse(result["capacity_evidence"]["evidence_authenticity_verified"])
            self.assertFalse(result["capacity_evidence"]["production_ready"])
            self.assertFalse(result["operations_plan"]["production_ready"])
            self.assertTrue((out/"capacity-evidence.json").is_file())


if __name__=="__main__":
    unittest.main()
