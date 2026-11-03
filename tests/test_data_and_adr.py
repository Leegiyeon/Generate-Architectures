"""Issue #12 후속: DB 접근 방식 / EC2 대안 / 인간 승인 ADR 일관성."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.architecture_advisor import decide
from scripts.architecture_decision_engine import (
    compare_architectures, build_decision_record, markdown_decision_record)
from scripts.data_access_decision import assess_data_access
from scripts.ec2_alternative import design_ec2_alternative
from scripts.evidence_contract import build_evidence_contract
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run
from scripts.aws_topology import design_aws_topology
from scripts.architecture_validator import validate_architecture


def sample(files, extra=None):
    context=tempfile.TemporaryDirectory()
    root=Path(context.name)
    for path, source in files.items():
        f=root/path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(source, encoding="utf-8")
    requirements=parse_requirements(None, root)
    specified=extra or {}
    requirements.update(specified)
    profile=inspect_repository(root)
    architecture=decide(profile, requirements)
    contract=build_evidence_contract(profile, {"nodes":[],"edges":[]},
                                    requirements, specified.keys(), architecture)
    topology=design_aws_topology(architecture, profile, requirements, contract)
    data=assess_data_access(profile, requirements, contract)
    choice=compare_architectures(architecture,profile,requirements,contract,
                                 topology,data_review=data)
    validation=validate_architecture(architecture,profile,requirements)
    adr=build_decision_record(architecture,validation,choice,data,contract)
    return context,requirements,profile,architecture,topology,data,choice,adr


class DataAndADRTests(unittest.TestCase):
    def test_mongodb_dependency_does_not_automigrate_to_documentdb(self):
        tmp,*items=sample(
            {"package.json":json.dumps({"dependencies":{"mongoose":"*"}}),
             "Dockerfile":"FROM node:22"}, {"data_access_pattern":"document_queries",
                                            "document_database_strategy":"keep_existing"})
        try:
            data=items[4]
            c={x["id"]:x for x in data["candidates"]}
            self.assertTrue(data["observed_document_indicator"])
            self.assertEqual(c["documentdb"]["status"],"blocked_for_migration")
            self.assertEqual(c["dynamodb"]["status"],"blocked_for_migration")
            self.assertIsNone(data["selected_data_store"])
            self.assertFalse(data["migration_approved_for_automatic_change"])
        finally:tmp.cleanup()

    def test_relational_transactions_without_sql_package_blocks_static_and_lambda_template(self):
        tmp,*items=sample(
            {"pyproject.toml":"[project]\nname='api'\n"},
            {"data_access_pattern":"relational_transactions"})
        try:
            decision=items[5]
            candidates={x["id"]:x for x in decision["candidates"]}
            self.assertIn("DEC-RDB-TEMPLATE",{i["rule_id"] for i in candidates["lambda"]["blockers"]})
            self.assertIn("DEC-STATIC-TRANSACTIONS",{i["rule_id"] for i in candidates["static"]["blockers"]})
        finally:tmp.cleanup()

    def test_migration_review_flag_is_not_database_autoapproval(self):
        tmp,*items=sample(
            {"package.json":json.dumps({"dependencies":{"mongoose":"*"}})},
            {"database_migration_approved": True, "data_access_pattern":"document_queries"})
        try:
            data=items[4]
            self.assertTrue(data["migration_review_requested"])
            self.assertFalse(data["migration_approved_for_automatic_change"])
            self.assertIsNone(data["selected_data_store"])
            self.assertFalse(any(x["approved"] for x in data["candidates"]))
        finally:tmp.cleanup()

    def test_user_declared_and_defaults_separated_in_adr(self):
        tmp,*items=sample({"Dockerfile":"FROM python:3.12"},
                          {"peak_rps":150,"data_access_pattern":"key_value"})
        try:
            adr=items[6]
            user_keys={x["key"] for x in adr["explicit_user_requirements"]}
            default_keys={x["key"] for x in adr["unconfirmed_defaults"]}
            self.assertIn("peak_rps",user_keys)
            self.assertNotIn("environment",user_keys)
            self.assertIn("environment",default_keys)
            self.assertEqual(adr["status"],"proposed_pending_human_approval")
            self.assertFalse(adr["approval"]["approved"])
            self.assertFalse(adr["automatic_deployment_allowed"])
            self.assertIn("승인 전",markdown_decision_record(adr))
        finally:tmp.cleanup()

    def test_ec2_alternative_keeps_vpc_rds_and_os_patch_review_separate(self):
        tmp,*items=sample(
            {"Dockerfile":"FROM node:22",
             "package.json":json.dumps({"dependencies":{"pg":"*"}})},
            {"requires_relational_database":True,
             "operations_preference":"high_availability",
             "egress_strategy":"nat_gateway","alb_scheme":"internal"})
        try:
            topo=items[3]
            ec2=design_ec2_alternative(topo,items[0])
            self.assertIsNotNone(ec2)
            ids={x["id"] for x in ec2["nodes"]}
            self.assertTrue({"ec2_a","ec2_b","asg","rds","rds_standby","alb"} <= ids)
            self.assertFalse(any("task_" in n or "vpce_" in n for n in ids))
            self.assertFalse(any(x.startswith("nat_") for x in ids))
            self.assertEqual(ec2["status"],"alternative_proposed_unverified")
            self.assertEqual(ec2["egress_strategy"],"undecided_for_ec2")
            self.assertIn("EC2-PATCH",{x["id"] for x in ec2["review_required"]})
            self.assertEqual(ec2["alb_scheme"],"internal")
        finally:tmp.cleanup()

    def test_ec2_alternative_missing_for_static_pattern(self):
        tmp,*items=sample({"vite.config.ts":"export default {}"})
        try:
            self.assertEqual(items[2]["option_id"],"static")
            self.assertIsNone(design_ec2_alternative(items[3],items[0]))
        finally:tmp.cleanup()

    def test_end_to_end_outputs_all_adr_and_ec2_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"app"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12")
            (root/"requirements.json").write_text(json.dumps({
                "requires_host_control":True,
                "data_access_pattern":"relational_transactions",
                "database_migration_approved":False,
                "container_port":8080,
                "operations_preference":"high_availability",
            }))
            out=Path(tmp)/"artifacts"
            result=run(root,out,requirements_file="requirements.json")
            self.assertEqual(result["option_id"],"containers")
            self.assertTrue(result["ec2_alternative"]["generated"])
            for file in ("data-access-decision.json","data-access-decision.md",
                         "decision-record.json","decision-record.md",
                         "ec2-alternative/aws-topology.svg",
                         "ec2-alternative/aws-topology.png",
                         "ec2-alternative/ec2-topology.json",
                         "ec2-alternative/ec2-alternative.md"):
                self.assertTrue((out/file).is_file(),file)
            adr=json.loads((out/"decision-record.json").read_text(encoding="utf-8"))
            self.assertFalse(adr["approval"]["approved"])
            doc=(out/"recommendation.md").read_text(encoding="utf-8")
            self.assertIn("16. 데이터 접근 방식과 최종 ADR",doc)
            self.assertIn("EC2 대안",doc)
            self.assertTrue((out/"aws-topology.svg").is_file())

    def test_bad_database_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            f=root/"req.json"
            for value in (
                {"data_access_pattern":"migrate_everything"},
                {"database_migration_approved":"yes"},
            ):
                f.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    parse_requirements("req.json",root)


if __name__=="__main__":
    unittest.main()
