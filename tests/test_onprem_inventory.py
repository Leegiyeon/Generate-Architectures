"""#34: 실제 온프레미스 진단을 주장하지 않는 선언형 As-Is 구성 검증."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.onprem_inventory import read_inventory, validate_inventory, assess_inventory
from scripts.render_onprem_as_is import render_as_is_svg
from scripts.recommend_architecture import run


def example():
    return {
        "schema_version": "1.0",
        "servers": [{
            "id": "app01", "role": "mixed", "os": "linux", "cpu_cores": 4,
            "memory_gb": 16, "storage_gb": 256, "db_engine": "postgresql",
            "access": "internal",
        }],
        "connections": [],
    }


class CheckLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.scripts = 0
    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts += 1
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href")


class InventoryTests(unittest.TestCase):
    def test_single_host_postgres_explicit_as_is_is_not_verified(self):
        data = validate_inventory(example())
        self.assertEqual(data["servers"][0]["source"], "user_declared_unverified")
        self.assertEqual(data["servers"][0]["db_engine"], "postgresql")
        self.assertEqual(data["servers"][0]["provided_fields"],
                         sorted(set(example()["servers"][0]) - {"id"}))
        profile = {"signals": {"relational_database": True, "docker": True}}
        result = assess_inventory(data, profile)
        self.assertEqual(result["status"], "declared_review_required")
        self.assertFalse(result["verified"])
        self.assertFalse(result["onprem_environment_checked"])
        self.assertFalse(result["migration_assessment_performed"])
        self.assertEqual(len(result["code_observations"]), 2)
        self.assertEqual(result["code_observations"][0]["source"],
                         "repository_code_signal")
        self.assertFalse(result["code_observations"][0]["deployment_location_verified"])
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "as-is.svg"
            drawing = render_as_is_svg(result, file)
            self.assertEqual(drawing["nodes"], 1)
            svg = ET.parse(file).getroot()
            self.assertTrue(svg.tag.endswith("svg"))
            text = file.read_text(encoding="utf-8")
            self.assertIn("app01", text)
            self.assertIn("PostgreSQL", text)
            self.assertNotIn("aws.amazon.com", text)
            self.assertNotIn("<script", text)

    def test_multiple_hosts_only_explicit_connections(self):
        data = example()
        data["servers"] = [
            {"id":"api01", "role":"application", "os":"linux", "access":"internal"},
            {"id":"db01", "role":"database", "os":"linux", "db_engine":"postgresql"}
        ]
        data["connections"] = [{"from":"api01","to":"db01","purpose":"database"}]
        doc = assess_inventory(validate_inventory(data), {"signals":{"relational_database":True}})
        self.assertEqual(len(doc["connections"]), 1)
        self.assertEqual(doc["connections"][0]["source"], "user_declared_unverified")
        self.assertEqual(doc["servers"][0]["db_engine"], "unknown")
        self.assertEqual(doc["servers"][0]["cpu_cores"], "unknown")
        self.assertEqual(len(doc["code_observations"]), 1)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"as-is.svg"
            render_as_is_svg(doc,output)
            txt=output.read_text(encoding="utf-8")
            self.assertIn("api01  →  db01",txt)
            self.assertIn("unknown",txt)
            self.assertEqual(txt.count("api01  →  db01"), 1)

    def test_missing_connections_does_not_create_any_edges(self):
        data = example()
        data["servers"].append({"id":"db01","role":"database","db_engine":"postgresql"})
        doc=assess_inventory(validate_inventory(data),{"signals":{}})
        self.assertFalse(doc["connections"])
        self.assertTrue(any("연결" in x for x in doc["questions"]))
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"a.svg"
            render_as_is_svg(doc,f)
            self.assertIn("연결 미입력",f.read_text(encoding="utf-8"))
            self.assertNotIn("app01  →  db01",f.read_text(encoding="utf-8"))

    def test_db_code_signal_not_equal_server_location(self):
        data = example()
        data["servers"][0]["db_engine"]="none"
        doc=assess_inventory(validate_inventory(data),
                             {"signals":{"relational_database":True}})
        self.assertEqual(doc["servers"][0]["db_engine"],"none")
        self.assertTrue(any("관계형 DB" in x for x in doc["questions"]))
        self.assertFalse(doc["verified"])

    def test_strict_schema_rejects_secrets_identifiers_bad_edges_bad_sizes(self):
        bad = []
        source = example()
        for unsafe in (
            {"ssh_password":"SECRET"},
            {"host":"10.0.0.8"}, {"ip":"192.168.0.4"}, {"port":5432},
            {"logs":"raw_log"}, {"firewall_acl":"0/0"},
            {"db_engine":"postgres"},
            {"access":"0.0.0.0/0"}, {"id":"server.example.com"},
            {"id":"172.16.0.1"}, {"id":"server<bad>"}, {"role":"ROOT"},
            {"integrations":["https://payments.example.com"]},
            {"integrations":["db01","db01"]},
            {"cpu_cores":float("nan")}, {"memory_gb":True},
            {"storage_gb":-1}, {"cpu_cores":None},
            {"constraints":["secret_password"]},
        ):
            dup=json.loads(json.dumps(source))
            dup["servers"][0].update(unsafe)
            bad.append(dup)
        bad.append({**source,"api_endpoint":"private"})
        bad.append({**source,"schema_version":"2.0"})
        bad.append({**source,"connections":[{"from":"app01","to":"unknown","purpose":"database"}]})
        bad.append({**source,"connections":[{"from":"app01","to":"app01","purpose":"database"}]})
        bad.append({**source,"connections":[{"from":"app01","to":"app01","purpose":"raw"}]})
        bad.append({**source,"servers":source["servers"]*2})
        bad.append({**source,"servers":[]})
        bad.append({**source,"servers":[{"id":"server"+str(i)} for i in range(9)]})
        for x in bad:
            with self.subTest(repr(x)[:100]), self.assertRaises(ValueError):
                validate_inventory(x)

    def test_reject_duplicate_object_keys_paths_symlinks_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=root/".architecture"
            folder.mkdir()
            path=folder/"onprem-inventory.json"
            path.write_text(json.dumps(example()),encoding="utf-8")
            self.assertEqual(read_inventory(root)["servers"][0]["id"],"app01")
            with self.assertRaises(ValueError):
                read_inventory(root,"../outside.json")
            bad=root/"duplicate.json"
            bad.write_text('{"schema_version":"1.0","schema_version":"2.0","servers":[],"connections":[]}')
            with self.assertRaises(ValueError):
                read_inventory(root,"duplicate.json")
            link=root/"link.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_inventory(root,"link.json")
            too_big=root/"large.json"
            too_big.write_text(" "*16385)
            with self.assertRaises(ValueError):
                read_inventory(root,"large.json")
            path.unlink()
            self.assertIsNone(read_inventory(root))
            with self.assertRaises(ValueError):
                read_inventory(root,".architecture/onprem-inventory.json")

    def test_no_inventory_migration_state_is_unverified_and_no_fake_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"project"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12")
            out=Path(tmp)/"out"
            result=run(root,out,analysis_goal="migrate_onprem")
            self.assertFalse(result["analysis_goal"]["onprem_inventory_analyzed"])
            self.assertEqual(result["onprem_as_is"]["status"],"needs_input")
            self.assertFalse(result["user_report"]["production_ready"])
            self.assertIn("현황 미확인",(out/"START-HERE.html").read_text(encoding="utf-8"))
            self.assertTrue((out/"as-is-inventory.json").is_file())
            self.assertTrue((out/"as-is-topology.svg").is_file())

    def test_full_pipeline_autodetects_default_inventory_and_preserves_other_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"project"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"requirements.txt").write_text("psycopg2-binary==2.9.10\n",encoding="utf-8")
            (root/".architecture").mkdir()
            (root/".architecture/onprem-inventory.json").write_text(
                json.dumps(example()), encoding="utf-8")
            out=Path(tmp)/"out"
            result=run(root,out,analysis_goal="migrate_onprem")
            self.assertTrue(result["analysis_goal"]["onprem_inventory_analyzed"])
            self.assertEqual(result["onprem_as_is"]["status"],"declared_review_required")
            goal=json.loads((out/"analysis-goal.json").read_text(encoding="utf-8"))
            self.assertTrue(goal["onprem_inventory_analyzed"])
            self.assertFalse(goal["migration_assessment_performed"])
            report=json.loads((out/"as-is-inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source"],"user_declared_unverified")
            self.assertEqual(report["servers"][0]["db_engine"],"postgresql")
            self.assertFalse(report["verified"])
            self.assertFalse(report["migration_assessment_performed"])
            self.assertEqual(result["option_id"],"containers")
            self.assertFalse(result["decision_record"]["approved"])
            page=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("온프레미스 현재 구성 As-Is — 사용자 선언",page)
            self.assertIn("PostgreSQL",page)
            self.assertIn("AWS To-Be",page)
            self.assertIn("as-is-inventory.md",page)
            self.assertIn("data:image/svg+xml;base64,",page)
            self.assertNotIn("<script",page)
            parsed=CheckLinks()
            parsed.feed(page)
            self.assertEqual(parsed.scripts,0)
            for path in parsed.links:
                self.assertTrue(path.startswith("#") or (out/path).is_file(),path)
            index=json.loads((out/"artifact-index.json").read_text(encoding="utf-8"))
            self.assertTrue(index["onprem_inventory_analyzed"])
            self.assertEqual(len(index["primary_files"]),5)
            self.assertEqual(len(index["supplementary_files"]),5) # As-Is 3개 + Migration Review 2개
            for item in index["supplementary_files"]:
                self.assertEqual(hashlib.sha256((out/item["path"]).read_bytes()).hexdigest(),
                                 item["sha256"])
            self.assertIn("사용자 직접 입력",(out/"START-HERE.md").read_text(encoding="utf-8"))
            self.assertTrue((out/"deliverables/01-aws-to-be.svg").is_file())

    def test_new_aws_cannot_silently_consume_onprem_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"app"
            root.mkdir()
            (root/"inventory.json").write_text(json.dumps(example()),encoding="utf-8")
            output=Path(tmp)/"report"
            with self.assertRaisesRegex(ValueError,"migrate_onprem"):
                run(root,output,analysis_goal="new_aws",onprem_inventory="inventory.json")
            self.assertFalse(output.exists())

    def test_explicit_inventory_path_is_supported_instead_of_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"app"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12")
            data=example()
            data["servers"][0]["id"]="custom01"
            (root/"custom.json").write_text(json.dumps(data),encoding="utf-8")
            out=Path(tmp)/"out"
            run(root,out,analysis_goal="migrate_onprem",onprem_inventory="custom.json")
            report=json.loads((out/"as-is-inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(report["servers"][0]["id"],"custom01")


if __name__ == "__main__":
    unittest.main()
