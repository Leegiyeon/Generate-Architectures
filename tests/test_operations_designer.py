"""Issue #13: AWS 보안·트래픽·운영 설계와 실제 To-Be 참조 무결성 회귀 테스트."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.architecture_advisor import decide
from scripts.aws_topology import design_aws_topology
from scripts.evidence_contract import build_evidence_contract
from scripts.operations_designer import design_operations, markdown_operations
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run


def fixture(inputs=None, repo_files=None):
    temp = tempfile.TemporaryDirectory()
    root=Path(temp.name)
    for name, value in (repo_files or {"Dockerfile":"FROM python:3.12"}).items():
        file=root/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value,encoding="utf-8")
    req=parse_requirements(None,root)
    explicit=inputs or {}
    req.update(explicit)
    profile=inspect_repository(root)
    architecture=decide(profile,req)
    contract=build_evidence_contract(profile, {"nodes":[],"edges":[]},
                                     req, explicit.keys(), architecture)
    topology=design_aws_topology(architecture,profile,req,contract)
    plan=design_operations(architecture,topology,req,contract)
    return temp,architecture,topology,plan,req,contract


class OperationsDesignerTests(unittest.TestCase):
    def test_default_container_has_no_invented_thresholds_or_operational_pass(self):
        temp,arch,topo,plan,req,contract=fixture()
        try:
            self.assertEqual(plan["selected_pattern"],"containers")
            self.assertFalse(plan["production_ready"])
            self.assertFalse(plan["account_checked"])
            self.assertFalse(plan["security_verified"])
            self.assertFalse(plan["slo_verified"])
            self.assertFalse(plan["scaling"]["load_tested"])
            self.assertFalse(plan["scaling"]["service_quotas_checked"])
            self.assertIsNone(plan["scaling"]["demand"]["peak_rps"])
            self.assertTrue(all(x["target_value"] is None and x["min_capacity"] is None
                                and x["max_capacity"] is None for x in plan["scaling"]["policies"]))
            self.assertTrue(all(x["threshold"] is None for x in plan["alerts"]))
            self.assertIn("Q-PEAK_RPS",{x["id"] for x in plan["questions"]})
            self.assertIn("Q-EGRESS",{x["id"] for x in plan["questions"]})
            self.assertIn("SG-ALB-443",{x["id"] for x in topo["network_controls"]})
            self.assertNotIn("REL-RDS-BACKUP",{x["id"] for x in plan["security_and_operations"]})
        finally:temp.cleanup()

    def test_production_two_az_rds_builds_security_alarms_and_recovery_review(self):
        temp,arch,topo,plan,req,contract=fixture(
            {
                "environment":"production",
                "availability_target_percent":99.95,
                "peak_rps":500, "average_rps":30,
                "latency_target_ms":400, "rto_minutes":60,
                "rpo_minutes":10, "requires_relational_database":True,
                "data_classification":"sensitive",
                "requires_authentication":True,
                "container_port":8080,"database_port":5432,
                "alb_scheme":"internet_facing",
                "egress_strategy":"nat_gateway",
                "external_outbound_required":True,
            }, {
                "Dockerfile":"FROM node:22",
                "package.json":json.dumps({"dependencies":{"pg":"*"}}),
            })
        try:
            ids={x["id"] for x in plan["security_and_operations"]}
            self.assertTrue({"SEC-IAM-LEAST","SEC-SG-CHAIN","SEC-SENSITIVE",
                             "SEC-AUTH","REL-RDS-BACKUP","REL-RDS-MULTIAZ",
                             "REL-2AZ-ECS","OPS-ECS-DEPLOY"} <= ids)
            self.assertTrue({"ALARM-RDS-CONNECTIONS","ALARM-RDS-FREESTORAGE",
                             "ALARM-ALB-5XX"} <= {x["id"] for x in plan["alerts"]})
            self.assertEqual(plan["scaling"]["demand"]["peak_rps"],500)
            self.assertEqual(plan["scaling"]["demand"]["rto_minutes"],60)
            self.assertEqual(plan["recovery"]["rpo_target_minutes"],10)
            self.assertFalse(plan["recovery"]["restore_tested"])
            self.assertFalse(plan["recovery"]["failover_tested"])
            self.assertEqual(len(plan["well_architected"]),6)
            self.assertTrue(all(x["status"]=="review_required" for x in plan["well_architected"]))
            self.assertTrue(all(set(x["topology_nodes"]) <= {n["id"] for n in topo["nodes"]}
                                for x in plan["security_and_operations"]))
            self.assertNotIn("Q-PEAK_RPS",{x["id"] for x in plan["questions"]})
            self.assertIn("민감 데이터 보호",markdown_operations(plan))
        finally:temp.cleanup()

    def test_internal_alb_policy_does_not_propose_public_edge(self):
        temp,arch,topo,plan,req,contract=fixture({"alb_scheme":"internal"})
        try:
            control_ids={x["id"] for x in plan["security_and_operations"]}
            self.assertIn("SEC-INTERNAL-EDGE",control_ids)
            self.assertNotIn("SEC-PUBLIC-EDGE",control_ids)
            self.assertEqual(topo["alb_scheme"],"internal")
            self.assertNotIn("igw",{n["id"] for n in topo["nodes"]})
        finally:temp.cleanup()

    def test_endpoint_only_external_conflict_not_treated_as_approved(self):
        temp,arch,topo,plan,req,contract=fixture({
            "alb_scheme":"internal", "egress_strategy":"vpc_endpoints_only",
            "external_outbound_required":True})
        try:
            self.assertEqual(topo["status"],"blocked_for_review")
            self.assertIn("SEC-EGRESS-CONFLICT",
                          {x["id"] for x in plan["security_and_operations"]})
            self.assertIn("Q-TOPOLOGY-BLOCK",{x["id"] for x in plan["questions"]})
            self.assertFalse(plan["production_ready"])
        finally:temp.cleanup()

    def test_static_cloudfront_not_covered_by_ecs_or_rds_ops(self):
        temp,arch,topo,plan,req,contract=fixture(
            repo_files={"vite.config.ts":"export default {}"})
        try:
            self.assertEqual(plan["selected_pattern"],"static")
            ids={x["id"] for x in plan["security_and_operations"]}
            self.assertIn("SEC-S3-OAC",ids)
            self.assertNotIn("SEC-SG-CHAIN",ids)
            self.assertNotIn("REL-RDS-BACKUP",ids)
            self.assertFalse(plan["scaling"]["policies"])
            self.assertEqual(plan["alerts"][0]["topology_node"],"cdn")
        finally:temp.cleanup()

    def test_serverless_lambda_monitors_quota_without_fake_capacity(self):
        temp,arch,topo,plan,req,contract=fixture(
            repo_files={"pyproject.toml":"[project]\nname='myapi'\n"})
        try:
            self.assertEqual(plan["selected_pattern"],"serverless")
            self.assertTrue({"ALARM-LAMBDA-ERROR","ALARM-LAMBDA-THROTTLES"} <=
                            {x["id"] for x in plan["alerts"]})
            pol=plan["scaling"]["policies"][0]
            self.assertEqual(pol["metric"],"ConcurrentExecutions")
            self.assertIsNone(pol["target_value"])
            self.assertFalse(pol["quota_checked"])
            self.assertIn("SEC-API-AUTH",{x["id"] for x in plan["security_and_operations"]})
        finally:temp.cleanup()

    def test_topology_sg_inconsistency_rejected_not_silently_patched(self):
        temp,arch,topo,plan,req,contract=fixture()
        try:
            bad={**topo, "network_controls":[]}
            with self.assertRaisesRegex(ValueError,"Security Group"):
                design_operations(arch,bad,req,contract)
            bad2={**topo, "edges":[x for x in topo["edges"]
                                  if not (x["source"]=="alb" and x["target"]=="task_a")]}
            with self.assertRaisesRegex(ValueError,"ALB"):
                design_operations(arch,bad2,req,contract)
        finally:temp.cleanup()

    def test_user_input_provenance_default_environment_not_user_selected(self):
        temp,arch,topo,plan,req,contract=fixture(
            {"peak_rps":0,"availability_target_percent":99.9})
        try:
            d=plan["scaling"]["demand"]
            self.assertEqual(d["peak_rps"],0)
            self.assertEqual(d["input_provenance"]["peak_rps"],"user_explicit")
            self.assertEqual(d["input_provenance"]["environment"],"system_default_or_missing")
            self.assertNotIn("Q-PEAK_RPS",{x["id"] for x in plan["questions"]})
            self.assertFalse(plan["slo_verified"])
        finally:temp.cleanup()

    def test_end_to_end_new_reports_and_recommendation_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)/"api"
            repo.mkdir()
            (repo/"Dockerfile").write_text("FROM python:3.12")
            (repo/"req.json").write_text(json.dumps({
                "peak_rps":1000,"operations_preference":"high_availability",
                "data_classification":"sensitive",
            }))
            out=Path(tmp)/"out"
            result=run(repo,out,requirements_file="req.json")
            self.assertTrue((out/"security-operations.json").is_file())
            self.assertTrue((out/"security-operations.md").is_file())
            self.assertFalse(result["operations_plan"]["production_ready"])
            content=json.loads((out/"security-operations.json").read_text(encoding="utf-8"))
            self.assertEqual(content["scaling"]["demand"]["peak_rps"],1000)
            self.assertFalse(content["scaling"]["thresholds_estimated"])
            self.assertIn("17. 보안·확장성·운영",
                          (out/"recommendation.md").read_text(encoding="utf-8"))
            self.assertTrue((out/"aws-topology.svg").is_file())


if __name__=="__main__":
    unittest.main()
