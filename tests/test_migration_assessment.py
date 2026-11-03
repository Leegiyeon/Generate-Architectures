"""Issue #35: 서버별 실제 선언 증거 기반 Rehost/Replatform 정적 검토 — 거짓 확정 금지."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.migration_assessment import assess_migration, markdown_migration
from scripts.onprem_inventory import assess_inventory, validate_inventory
from scripts.recommend_architecture import run


def inventory(servers=None, connections=None):
    return validate_inventory({
        "schema_version": "1.0",
        "servers": servers if servers is not None else [
            {"id": "api01", "role": "mixed", "os": "linux",
             "db_engine": "postgresql", "cpu_cores": 4,
             "memory_gb": 16, "storage_gb": 256, "access": "internal"}
        ],
        "connections": connections or [],
    })


def draft(data=None, signals=None, req=None, cost=None):
    signal = {"signals": signals if signals is not None else {"docker": True}}
    state = assess_inventory(data or inventory(), signal)
    return assess_migration(state, signal, req or {}, {"pattern": "containers"},
                            cost or {"status": "needs_input"})


class MigrationAssessmentTests(unittest.TestCase):
    def test_missing_inventory_does_not_create_false_strategy(self):
        value = assess_migration(
            assess_inventory(None, {"signals": {}}), {"signals": {}},
            {}, {"pattern": "containers"}, {"status": "needs_input"}
        )
        self.assertEqual(value["status"], "needs_inventory")
        self.assertEqual(value["strategies"], [])
        self.assertEqual(value["checklist"], [])
        self.assertIsNone(value["recommended_strategy"])
        self.assertFalse(value["migration_ready"])
        self.assertIn("입력 필요", markdown_migration(value))

    def test_single_host_rehost_replatform_each_has_explicit_different_mapping(self):
        value = draft()
        self.assertEqual(value["status"], "assessment_draft_review_required")
        self.assertEqual([x["id"] for x in value["strategies"]], ["rehost", "replatform"])
        rehost, replatform = value["strategies"]
        self.assertEqual(rehost["changes"][0]["decision"], "relocate")
        self.assertIn("Amazon EC2", rehost["changes"][0]["to_be_candidate"])
        self.assertEqual(len(replatform["changes"]), 2)
        self.assertEqual([x["component"] for x in replatform["changes"]],
                         ["application", "database"])
        self.assertEqual(replatform["changes"][0]["decision"], "modify")
        self.assertIn("ECS", replatform["changes"][0]["to_be_candidate"])
        self.assertIn("Amazon RDS for postgresql", replatform["changes"][1]["to_be_candidate"])
        self.assertTrue(all(not x["validated"] for x in replatform["changes"]))
        self.assertTrue(all(not x["approved"] for x in value["strategies"]))
        self.assertFalse(value["migration_approved"])
        self.assertFalse(value["migration_ready"])
        self.assertIsNone(value["recommended_strategy"])
        self.assertIsNone(value["estimated_monthly_migration_cost_usd"])
        self.assertIsNone(value["cutover_downtime_minutes"])
        self.assertIn("MIG-DATA", value["blocking_risk_ids"])
        ref = replatform["changes"][0]["evidence"]
        self.assertEqual(ref[0]["ref"], "as-is-inventory.json#/servers/0")
        self.assertEqual(ref[0]["type"], "user_declared_unverified")
        self.assertEqual(ref[1]["ref"], "repository-analysis.json#/signals/docker")
        self.assertEqual(len(value["checklist"]), 6)

    def test_db_package_observation_does_not_assign_db_to_server(self):
        state = inventory([
            {"id": "api01", "role": "application", "os": "linux",
             "db_engine": "none", "access": "internal"}
        ])
        value = draft(state, {"relational_database": True, "docker": False})
        changes = value["strategies"][1]["changes"]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["decision"], "unknown")
        self.assertFalse(any("Amazon RDS" in x["to_be_candidate"] for x in changes))
        risk = next(x for x in value["risks"] if x["id"] == "MIG-CONFLICT-DB")
        self.assertEqual(risk["severity"], "blocker")
        self.assertIn("repository-analysis.json#/signals/relational_database",
                      risk["evidence"])

    def test_db_engine_on_app_role_not_silently_dropped(self):
        state=inventory([{"id":"app01","role":"application","os":"linux",
                          "db_engine":"mysql"}])
        value=draft(state,{"docker":True})
        self.assertEqual([x["component"] for x in value["strategies"][1]["changes"]],
                         ["application", "database"])
        self.assertIn("mysql",value["strategies"][1]["changes"][1]["to_be_candidate"])

    def test_windows_app_and_unknown_os_are_not_forced_to_fargate(self):
        data=inventory([
            {"id":"win01","role":"application","os":"windows","db_engine":"unknown"},
            {"id":"unk01","role":"application","os":"unknown","db_engine":"none"},
        ])
        value=draft(data,{"docker":True})
        found = {x["server_id"]:x for x in value["strategies"][1]["changes"]}
        self.assertEqual(found["win01"]["decision"], "unknown")
        self.assertNotIn("Fargate",found["win01"]["to_be_candidate"])
        self.assertEqual(found["unk01"]["decision"], "unknown")
        self.assertIn("MIG-OS",value["blocking_risk_ids"])

    def test_mongodb_does_not_claim_documentdb_compatibility(self):
        data=inventory([{"id":"mdb01","role":"database","os":"linux",
                         "db_engine":"mongodb"}])
        value=draft(data,{"document_database":True})
        to_be=value["strategies"][1]["changes"][0]
        self.assertEqual(to_be["decision"],"unknown")
        self.assertIn("MongoDB 유지",to_be["to_be_candidate"])
        self.assertIn("DocumentDB",to_be["reason"])
        self.assertIn("완전 동일",to_be["reason"])
        self.assertNotIn("Amazon RDS",to_be["to_be_candidate"])

    def test_file_storage_is_not_silently_moved_to_s3(self):
        data=inventory([{"id":"store01","role":"storage","os":"linux",
                         "db_engine":"none","storage_gb":1000}])
        value=draft(data,{"docker":False})
        change=value["strategies"][1]["changes"][0]
        self.assertEqual(change["decision"],"unknown")
        self.assertIn("EBS / EFS / S3",change["to_be_candidate"])
        self.assertIsNone(value["cutover_downtime_minutes"])

    def test_constraints_and_internal_network_create_source_backed_risks(self):
        data=inventory([{"id":"app01","role":"mixed","os":"linux","db_engine":"oracle",
                        "access":"internal","integrations":["payment"],
                        "constraints":["licensed_software","local_hardware",
                                       "legacy_runtime","downtime_sensitive",
                                       "regulated_data"]}])
        value=draft(data,{"docker":True},{"rto_minutes":20,"rpo_minutes":5})
        ids={x["id"] for x in value["risks"]}
        for x in ("MIG-HYBRID","MIG-LICENSE","MIG-HARDWARE","MIG-LEGACY",
                  "MIG-REGULATION","MIG-CUTOVER","MIG-DATA","MIG-EXTERNAL",
                  "MIG-DR-TEST"):
            self.assertIn(x, ids)
        self.assertNotIn("MIG-RTO-RPO",ids)
        self.assertFalse(value["data_transfer_verified"])
        self.assertIsNone(value["recommended_strategy"])

    def test_missing_links_and_unknown_db_do_not_invent_server_network(self):
        data=inventory([
            {"id":"api01","role":"application","os":"linux","db_engine":"unknown"},
            {"id":"db01","role":"database","os":"linux","db_engine":"unknown"},
        ])
        value=draft(data,{"relational_database":True})
        self.assertIn("MIG-LINK", value["blocking_risk_ids"])
        self.assertIn("MIG-DB", value["blocking_risk_ids"])
        self.assertFalse(any(x["decision"] == "modify" and
                             "Amazon RDS" in x["to_be_candidate"]
                             for x in value["strategies"][1]["changes"]))

    def test_cost_from_other_aws_scenario_is_not_migration_cost(self):
        value = draft(cost={"status":"scenario_estimate","monthly_total_usd":"10000"})
        self.assertEqual(value["pricing_reference_status"],"scenario_estimate")
        self.assertIsNone(value["estimated_monthly_migration_cost_usd"])
        self.assertTrue(all(c["cost_usd"] is None for c in value["strategies"]))
        self.assertIn("미산정",markdown_migration(value))

    def test_full_pipeline_draft_exists_separate_from_code_and_aws_to_be(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"project"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"requirements.txt").write_text("psycopg2-binary==2.9.10\n",encoding="utf-8")
            (root/".architecture").mkdir()
            (root/".architecture/onprem-inventory.json").write_text(json.dumps({
                "schema_version":"1.0",
                "servers":[{"id":"api01","role":"application","os":"linux",
                            "db_engine":"none","access":"internal"},
                           {"id":"db01","role":"database","os":"linux",
                            "db_engine":"postgresql","access":"internal"}],
                "connections":[{"from":"api01","to":"db01","purpose":"database"}],
            }),encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,analysis_goal="migrate_onprem")
            report=json.loads((out/"migration-assessment.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"],"assessment_draft_review_required")
            self.assertTrue(result["analysis_goal"]["migration_review_generated"])
            self.assertEqual(result["migration_assessment"]["status"],report["status"])
            self.assertFalse(result["migration_assessment"]["verified"])
            self.assertFalse(result["decision_record"]["approved"])
            self.assertFalse(result["user_report"]["production_ready"])
            self.assertFalse(report["migration_ready"])
            goal=json.loads((out/"analysis-goal.json").read_text(encoding="utf-8"))
            self.assertTrue(goal["migration_review_generated"])
            self.assertFalse(goal["migration_assessment_performed"])
            html=(out/"START-HERE.html").read_text(encoding="utf-8")
            for fragment in ("Rehost / Replatform", "변경사항", "Cutover",
                             "Rollback", "migration-assessment.md",
                             "as-is-topology.svg", "AWS To-Be"):
                self.assertIn(fragment,html)
            self.assertNotIn("<script",html)
            self.assertIn("Rehost", (out/"START-HERE.md").read_text(encoding="utf-8"))
            self.assertIn("MIG-DATA",(out/"migration-assessment.md").read_text(encoding="utf-8"))
            self.assertEqual(len(json.loads((out/"artifact-index.json")
                          .read_text(encoding="utf-8"))["supplementary_files"]),5)
            self.assertTrue((out/"deliverables/01-aws-to-be.svg").is_file())

    def test_missing_inventory_still_blocks_migration_in_full_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"app"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,analysis_goal="migrate_onprem")
            self.assertEqual(result["migration_assessment"]["status"],"needs_inventory")
            self.assertFalse(result["analysis_goal"]["migration_review_generated"])
            self.assertIsNone(json.loads((out/"migration-assessment.json")
                               .read_text(encoding="utf-8"))["recommended_strategy"])
            self.assertNotIn("id='migration-assessment'",
                             (out/"START-HERE.html").read_text(encoding="utf-8"))
            self.assertIn("현황 미확인",(out/"START-HERE.html").read_text(encoding="utf-8"))

    def test_new_aws_mode_does_not_add_migration_ui_or_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"app"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,analysis_goal="new_aws")
            self.assertNotIn("migration_assessment",result)
            self.assertFalse((out/"migration-assessment.json").exists())
            self.assertNotIn("id='migration-assessment'",
                             (out/"START-HERE.html").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
