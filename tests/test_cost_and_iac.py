"""비용 계산의 출처·불완전성 및 Terraform 계획의 보안/민감정보 비노출 검증."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.cost_estimator import read_cost_inputs, estimate_costs
from scripts.iac_policy_validator import read_terraform_plan, inspect_terraform_plan
from scripts.recommend_architecture import run


def quote(qty="10", rate="0.25", as_of="2026-11-01"):
    return {"id": "unit", "quantity": qty, "unit": "GB",
            "rate": {"kind": "manual_quote", "unit_price_usd": rate,
                     "source": "https://aws.amazon.com/s3/pricing/", "as_of": as_of}}


def plan(changes):
    return {"format_version": "1.2", "resource_changes": changes}


def change(type_name, value, unknown=None, actions=None):
    return {"address": "a_credential_never_leak", "mode": "managed", "type": type_name,
            "change": {"actions": actions or ["create"], "after": value,
                       "after_unknown": unknown or {}}}


def aws_rate_record(region="ap-northeast-2", unit="Requests", price="0.0000002", tier=False):
    dims = {
        "request": {"unit": unit, "beginRange": "0", "endRange": "100000" if tier else "Inf",
                    "pricePerUnit": {"USD": price}},
    }
    return json.dumps({
        "product": {"attributes": {"regionCode": region}},
        "terms": {"OnDemand": {"abc": {"priceDimensions": dims}}},
    })


class CostEstimatorTests(unittest.TestCase):
    def test_missing_input_does_not_show_zero(self):
        result = estimate_costs(None)
        self.assertEqual(result["status"], "needs_input")
        self.assertIsNone(result["monthly_total_usd"])
        self.assertFalse(result["complete"])

    def test_exact_manual_quote_arithmetic_no_hidden_rounding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = {"region": "ap-northeast-2", "items": [quote("10", "0.1234")]}
            (root/"cost.json").write_text(json.dumps(data))
            inputs = read_cost_inputs(root, "cost.json")
            result = estimate_costs(inputs)
            self.assertTrue(result["complete"])
            self.assertEqual(result["monthly_total_usd"], "1.2340")
            self.assertEqual(result["lines"][0]["rate_source"], "manual_quote")
            self.assertIn("실제 청구액", result["note"])

    def test_unpriced_item_disables_total(self):
        result = estimate_costs({"region": "ap-northeast-2", "items": [
            quote(), {"id": "other", "quantity": 100, "unit": "Requests",
                      "rate": {"kind": "unknown"}},
        ]})
        self.assertEqual(result["unpriced_count"], 1)
        self.assertIsNone(result["monthly_total_usd"])
        self.assertEqual(result["priced_subtotal_usd"], "2.50")

    def test_live_query_requires_explicit_opt_in_and_exact_sku(self):
        class Client:
            def __init__(self): self.calls = []
            def get_products(self, **kwargs):
                self.calls.append(kwargs)
                return {"PriceList": [aws_rate_record()]}
        config = {"region": "ap-northeast-2", "items": [{
            "id": "lambda", "quantity": 1000000, "unit": "Requests",
            "rate": {"kind": "aws_price_list", "service_code": "AWSLambda",
                     "filters": {"group": "AWS-Lambda-Requests"}},
        }]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"cost.json").write_text(json.dumps(config))
            parsed = read_cost_inputs(root, "cost.json")
        client = Client()
        disabled = estimate_costs(parsed, live=False, client=client)
        self.assertIsNone(disabled["monthly_total_usd"])
        self.assertEqual(client.calls, [])
        enabled = estimate_costs(parsed, live=True, client=client)
        self.assertEqual(enabled["monthly_total_usd"], "0.2000000")
        filters = {x["Field"]: x["Value"] for x in client.calls[0]["Filters"]}
        self.assertEqual(filters["regionCode"], "ap-northeast-2")

    def test_reject_ambiguous_or_tiered_prices(self):
        class Fake:
            def get_products(self, **kwargs):
                return {"PriceList": [aws_rate_record(tier=True)]}
        config = {"region": "ap-northeast-2", "items": [{
            "id": "lambda", "quantity": 10, "unit": "Requests",
            "rate": {"kind": "aws_price_list", "service_code": "AWSLambda",
                     "filters": {"group": "AWS-Lambda-Requests"}},
        }]}
        result = estimate_costs(config, live=True, client=Fake())
        self.assertIsNone(result["monthly_total_usd"])
        self.assertEqual(result["lines"][0]["status"], "unpriced")

    def test_inputs_reject_bad_rate_and_path_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for invalid in (quote("-1"), quote("10", "NaN")):
                (root/"cost.json").write_text(json.dumps({"region": "ap-northeast-2",
                                                         "items": [invalid]}))
                with self.assertRaises(ValueError):
                    read_cost_inputs(root, "cost.json")
            with self.assertRaises(ValueError):
                read_cost_inputs(root, "../private.json")


class TerraformPolicyTests(unittest.TestCase):
    def test_no_plan_is_not_scanned(self):
        r = inspect_terraform_plan(None)
        self.assertEqual(r["status"], "not_scanned")
        self.assertFalse(r["production_ready"])

    def test_public_db_admin_ports_open_bucket_and_wildcard_iam(self):
        resources = [
            change("aws_security_group", {"ingress": [{
                "cidr_blocks": ["0.0.0.0/0"], "from_port": 22, "to_port": 22,
                "protocol": "tcp"}]}),
            change("aws_db_instance", {"publicly_accessible": True,
                                       "storage_encrypted": False}),
            change("aws_s3_bucket_acl", {"acl": "public-read"}),
            change("aws_iam_policy", {"policy": json.dumps({"Statement": [
                {"Effect": "Allow", "Action": "*", "Resource": "*"}]})}),
            change("aws_s3_bucket_public_access_block", {"block_public_policy": False}),
        ]
        resources[0]["change"]["after"]["internal_secret"]="NEVER_SHOW_ME"
        report = inspect_terraform_plan(plan(resources))
        rules = {x["rule_id"] for x in report["findings"]}
        self.assertTrue({"TF-SEC-001", "TF-SEC-003", "TF-SEC-004", "TF-SEC-005",
                         "TF-SEC-006", "TF-SEC-007"}.issubset(rules))
        flat=json.dumps(report)
        self.assertNotIn("NEVER_SHOW_ME",flat)
        self.assertNotIn("a_credential_never_leak",flat)
        self.assertFalse(report["production_ready"])

    def test_open_443_is_review_not_auto_critical(self):
        report = inspect_terraform_plan(plan([change("aws_security_group", {"ingress": [
            {"cidr_blocks": ["0.0.0.0/0"], "from_port": 443, "to_port": 443, "protocol": "tcp"}
        ]})]))
        self.assertEqual(report["findings"][0]["rule_id"], "TF-SEC-002")

    def test_unknown_or_uncovered_not_passed(self):
        report = inspect_terraform_plan(plan([
            change("aws_db_instance", {}, unknown={"publicly_accessible": True}),
            change("aws_unsupported_resource", {"token": "private"}),
        ]))
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["scanned_supported_resources"], 1)
        self.assertEqual(report["findings"][0]["rule_id"], "TF-SEC-008")

    def test_secret_plan_not_written_as_artefact(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"Dockerfile").write_text("FROM python:3.12")
            plan_file=root/"terraform-plan.json"
            plan_file.write_text(json.dumps(plan([
                change("aws_db_instance", {"publicly_accessible": True,
                                           "password": "VERY_SENSITIVE_SECRET"})])))
            report=inspect_terraform_plan(read_terraform_plan(root,"terraform-plan.json"))
            self.assertNotIn("VERY_SENSITIVE_SECRET",json.dumps(report))
            out=root/"output"
            result=run(root,out,terraform_plan="terraform-plan.json")
            self.assertEqual(result["iac_review"]["critical_findings"],1)
            for f in ("iac-policy.json","iac-policy.md","cost-estimate.json","cost-estimate.md"):
                self.assertTrue((out/f).exists())
                self.assertNotIn("VERY_SENSITIVE_SECRET",(out/f).read_text(encoding="utf-8"))
            self.assertIsNone(result["cost_estimate"]["monthly_total_usd"])


if __name__ == "__main__":
    unittest.main()
