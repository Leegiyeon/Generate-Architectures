"""P0 #11 후속: AWS 아이콘+AZ 통합, 명시적 NAT/Endpoint/SG 정책 테스트."""
import html
import json
from pathlib import Path
import tempfile
import unittest

from scripts.architecture_advisor import decide
from scripts.aws_topology import design_aws_topology
from scripts.evidence_contract import build_evidence_contract
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.render_aws_topology import render_aws_topology
from scripts.recommend_architecture import run
from scripts.topology_network_policy import RULES, markdown_network_policy


def scenario(tmp, requirements, files=None):
    root = Path(tmp)
    for file, content in (files or {"Dockerfile": "FROM python:3.12"}).items():
        target = root / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    profile = inspect_repository(root)
    baseline = parse_requirements(None, root)
    baseline.update(requirements)
    design = decide(profile, baseline)
    contract = build_evidence_contract(profile, {"nodes": [], "edges": []},
                                       baseline, requirements.keys(), design)
    return design_aws_topology(design, profile, baseline, contract)


class NetworkPolicyTests(unittest.TestCase):
    def test_unanswered_inputs_remain_review_not_approved_network_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {})
            self.assertEqual(t["egress_strategy"], "undecided")
            self.assertEqual(t["alb_scheme"], "internet_facing")
            self.assertIn("igw", {n["id"] for n in t["nodes"]})
            codes = {r["id"] for r in t["review_required"]}
            self.assertTrue({"NET-EGRESS-CHOICE", "NET-ALB-SCHEME",
                             "NET-APP-PORT", "NET-EXTERNAL-UNKNOWN"} <= codes)
            self.assertEqual(t["status"], "proposed_unverified")
            self.assertTrue(any(x["target"] == "not_selected"
                                for x in t["route_intents"]))
            self.assertTrue(all(x["validated"] is False for x in t["route_intents"]))
            self.assertEqual(next(x for x in t["network_controls"]
                                  if x["id"] == "SG-APP-A")["port"], None)
            self.assertFalse(any(x["id"].startswith("nat_") for x in t["nodes"]))

    def test_high_availability_nat_uses_two_azs_and_rds_sg_is_restricted(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {
                "egress_strategy": "nat_gateway",
                "alb_scheme": "internet_facing",
                "container_port": 3000,
                "database_port": 5432,
                "requires_relational_database": True,
                "operations_preference": "high_availability",
                "region": "ap-northeast-2",
                "external_outbound_required": True,
            }, {
                "Dockerfile": "FROM node:22",
                "package.json": json.dumps({"dependencies": {"pg": "1.0.0"}}),
            })
            n = {x["id"]: x for x in t["nodes"]}
            self.assertTrue({"igw", "nat_a", "nat_b", "task_a", "task_b",
                             "rds", "rds_standby"} <= set(n))
            self.assertEqual(n["nat_a"]["parent"], "public_a")
            self.assertEqual(n["nat_b"]["parent"], "public_b")
            self.assertTrue(t["high_availability_proposed"])
            controls = {x["id"]: x for x in t["network_controls"]}
            self.assertEqual(controls["SG-APP-A"]["port"], 3000)
            self.assertEqual(controls["SG-APP-B"]["source_scope"], "alb_sg_only")
            self.assertEqual(controls["SG-DB-B"]["port"], 5432)
            self.assertEqual(controls["SG-DB-A"]["source_scope"], "ecs_sg_only")
            self.assertTrue(any(x["source"] == "app_b" and x["target"] == "nat_b"
                                for x in t["route_intents"]))
            self.assertIn("NET-NAT-COST", {x["id"] for x in t["review_required"]})
            self.assertNotIn("NET-EGRESS-CONFLICT", {x["id"] for x in t["review_required"]})
            self.assertTrue(all(x["status"] == "proposed_not_deployed" for x in t["nodes"]))

    def test_endpoint_only_does_not_satisfy_external_internet_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {
                "egress_strategy": "vpc_endpoints_only",
                "external_outbound_required": True,
                "alb_scheme": "internal",
            })
            ids = {x["id"] for x in t["nodes"]}
            self.assertIn("vpce_ecr_api", ids)
            self.assertIn("vpce_ecr_dkr", ids)
            self.assertIn("vpce_s3_gateway", ids)
            self.assertIn("vpce_logs", ids)
            self.assertIn("vpce_secrets", ids)
            self.assertNotIn("igw", ids)
            self.assertFalse(any(x.startswith("nat_") for x in ids))
            self.assertEqual(t["status"], "blocked_for_review")
            self.assertIn("NET-EGRESS-CONFLICT",
                          {x["id"] for x in t["review_required"]})
            self.assertIn("SG-ALB-443", {x["id"] for x in t["network_controls"]})
            self.assertEqual(t["network_controls"][0]["source_scope"], "private_client")

    def test_internal_alb_is_not_drawn_on_public_subnets(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {"alb_scheme": "internal",
                               "external_outbound_required": False})
            ids = {x["id"] for x in t["nodes"]}
            self.assertNotIn("igw", ids)
            placement = {(e["source"], e["target"]) for e in t["edges"]
                         if e["kind"] == "placement"}
            self.assertIn(("alb", "app_a"), placement)
            self.assertIn(("alb", "app_b"), placement)
            self.assertNotIn(("alb", "public_a"), placement)
            self.assertIn("NET-INTERNAL-ENTRY",
                          {x["id"] for x in t["review_required"]})

    def test_network_rules_and_sources_complete_for_each_node_and_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {"egress_strategy": "nat_plus_endpoints",
                               "operations_preference": "high_availability"})
            for item in t["nodes"] + t["edges"]:
                self.assertTrue(item["design_rule_ids"], item)
                self.assertTrue(set(item["design_rule_ids"]) <= RULES.keys())
            self.assertEqual(t["counts"]["nodes"], len(t["nodes"]))
            self.assertEqual(t["counts"]["edges"], len(t["edges"]))
            self.assertIn("Private outbound", markdown_network_policy(t))

    def test_topology_svg_embeds_aws_icons_and_az_subnet_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = scenario(tmp, {"egress_strategy": "nat_gateway",
                               "operations_preference": "high_availability",
                               "requires_relational_database": True})
            with tempfile.TemporaryDirectory() as out:
                rendered = render_aws_topology(t, out)
                svg = rendered["svg"].read_text(encoding="utf-8")
                self.assertGreater(rendered["embedded_icons"], 3)
                self.assertIn("data:image/png;base64,", svg)
                self.assertIn("AZ-A", html.unescape(svg))
                self.assertIn("Public Subnet A", html.unescape(svg))
                self.assertIn("Private DB Subnet B", html.unescape(svg))
                self.assertIn("Internet Gateway", html.unescape(svg))
                self.assertTrue(rendered["png"].read_bytes().startswith(bytes([137,80,78,71])))

    def test_full_pipeline_writes_network_review_and_icon_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            (root / "Dockerfile").write_text("FROM python:3.12")
            (root / "requirements.json").write_text(json.dumps({
                "alb_scheme": "internal", "egress_strategy": "vpc_endpoints_only",
                "external_outbound_required": True, "container_port": 8080,
            }))
            out = Path(tmp) / "result"
            result = run(root, out, requirements_file="requirements.json")
            self.assertTrue((out / "network-policy.md").is_file())
            self.assertGreater(result["aws_topology"]["embedded_icons"], 0)
            self.assertEqual(result["aws_topology"]["status"], "blocked_for_review")
            topology = json.loads((out / "aws-topology.json").read_text(encoding="utf-8"))
            self.assertEqual(topology["status"], "blocked_for_review")
            self.assertTrue((out / "architecture.svg").is_file())
            self.assertTrue((out / "aws-topology.svg").is_file())

    def test_input_validation_rejects_unsafe_port_and_unsupported_egress(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "req.json"
            for value in (
                {"container_port": 0},
                {"database_port": 65536},
                {"egress_strategy": "s3_public"},
                {"alb_scheme": "world_open"},
                {"external_outbound_required": "true"},
            ):
                file.write_text(json.dumps(value))
                with self.assertRaises(ValueError, msg=str(value)):
                    parse_requirements("req.json", tmp)


if __name__ == "__main__":
    unittest.main()
