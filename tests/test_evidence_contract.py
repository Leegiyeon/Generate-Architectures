"""근거/가정/요구사항 출처 및 반복 질문 회귀 테스트."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.application_graph import build_application_graph
from scripts.architecture_advisor import decide
from scripts.ai_architecture_agent import build_context
from scripts.evidence_contract import build_evidence_contract, markdown_evidence
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run


def repo_with(tmp, files):
    root = Path(tmp)
    for path, data in files.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data, encoding="utf-8")
    return root


def contract_for(root, path=None):
    profile = inspect_repository(root)
    graph = build_application_graph(root)
    requirements, explicit = parse_requirements(
        path, root, return_provenance=True)
    architecture = decide(profile, requirements)
    contract = build_evidence_contract(
        profile, graph, requirements, explicit, architecture)
    return contract, profile, graph, requirements, explicit, architecture


class EvidenceContractTests(unittest.TestCase):
    def test_explicit_inputs_not_confused_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_with(tmp, {
                "Dockerfile": "FROM python:3.12",
                ".architecture/requirements.json": json.dumps({
                    "region": "ap-northeast-2",
                    "average_rps": 10,
                    "peak_rps": 200,
                    "peak_concurrent_connections": 30,
                    "data_classification": "internal",
                    "operations_preference": "minimize_maintenance",
                    "requires_authentication": False,
                }),
            })
            contract, profile, graph, reqs, explicit, arch = contract_for(
                root, ".architecture/requirements.json")
            requested = {r["key"] for r in contract["user_requirements"]}
            defaults = {r["key"] for r in contract["system_defaults"]}
            self.assertIn("region", requested)
            self.assertIn("peak_rps", requested)
            self.assertIn("operations_preference", requested)
            self.assertNotIn("environment", requested)
            self.assertIn("environment", defaults)
            self.assertEqual(reqs["environment"], "dev")
            questions = {u["key"] for u in contract["unknowns"]}
            for answered in ("peak_rps", "average_rps",
                             "peak_concurrent_connections",
                             "region", "data_classification",
                             "requires_authentication"):
                self.assertNotIn(answered, questions)
            self.assertEqual(contract["status"], "static_only")
            self.assertTrue(contract["analyzed_at_utc"].endswith("+00:00"))

    def test_auth_dependency_avoids_reasking_auth_without_false_certainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=repo_with(tmp, {
                "package.json": json.dumps({"dependencies":{"passport":"*","pg":"*"}}),
            })
            contract, profile, graph, reqs, explicit, arch=contract_for(root)
            self.assertTrue(profile["signals"]["authentication_library"])
            self.assertTrue(profile["signals"]["relational_database"])
            missing={u["key"] for u in contract["unknowns"]}
            self.assertNotIn("requires_authentication",missing)
            self.assertNotIn("database_requirement",missing)
            indicator={x["signal"]:x for x in contract["configuration_inferences"]}
            self.assertEqual(indicator["authentication_library"]["certainty"],
                             "configuration_indicator")
            self.assertFalse(indicator["authentication_library"]["runtime_verified"])

    def test_ast_paths_and_lines_are_observations_not_runtime_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=repo_with(tmp,{
                "app.py": "from fastapi import FastAPI\napp=FastAPI()\n"
                          "@app.get('/hello')\ndef hello():\n    return 'ok'\n",
                "Dockerfile": "FROM python:3.12",
            })
            contract,profile,graph,req,explicit,arch=contract_for(root)
            endpoints=[f for f in contract["observations"] if f["category"]=="ast_route"]
            self.assertEqual(len(endpoints),1)
            self.assertEqual(endpoints[0]["source"]["path"],"app.py")
            self.assertEqual(endpoints[0]["source"]["line"],3)
            self.assertEqual(endpoints[0]["certainty"],"static_observed")
            self.assertFalse(endpoints[0]["runtime_verified"])
            self.assertNotIn("사용자가", json.dumps(endpoints,ensure_ascii=False))
            self.assertIn("설계 가정",markdown_evidence(contract))

    def test_error_is_partial_and_missing_signal_not_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=repo_with(tmp,{"Dockerfile":"FROM python:3.12"})
            c,profile,graph,req,explicit,arch=contract_for(root)
            graph["errors"]=[{"path":"src/broken.ts","kind":"parse_failed"}]
            broken=build_evidence_contract(profile,graph,req,explicit,arch)
            self.assertEqual(broken["status"],"partial")
            self.assertEqual(broken["coverage"]["graph_parser_errors"],1)
            missing={u["key"] for u in broken["unknowns"]}
            self.assertIn("database_requirement",missing)
            self.assertIn("requires_authentication",missing)
            self.assertTrue(any("미탐지" in x for x in broken["limitations"]))

    def test_reject_peak_rps_below_average_and_bad_operations_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/"requirements.json"
            p.write_text(json.dumps({"average_rps":100,"peak_rps":20}))
            with self.assertRaisesRegex(ValueError,"peak_rps"):
                parse_requirements("requirements.json",root)
            p.write_text(json.dumps({"operations_preference":["invalid"]}))
            with self.assertRaises(ValueError):
                parse_requirements("requirements.json",root)

    def test_ai_context_excludes_defaults_and_raw_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=repo_with(tmp,{
                "app.py":"def confidential_function():\n    pass\n",
                "Dockerfile":"FROM python:3.12",
                "requirements.json":json.dumps({"peak_rps":150,"region":"ap-northeast-2"}),
            })
            c,p,g,r,explicit,a=contract_for(root,"requirements.json")
            payload=build_context(p,g,r,a,explicit_requirements=explicit)
            clean=json.dumps(payload)
            requirement_keys={x["key"] for x in payload["evidence"] if x["kind"]=="requirement"}
            self.assertIn("peak_rps",requirement_keys)
            self.assertIn("region",requirement_keys)
            self.assertNotIn("environment",requirement_keys)
            self.assertNotIn("data_classification",requirement_keys)
            self.assertNotIn("confidential_function",clean)
            self.assertNotIn("app.py",clean)


    def test_user_confirmed_rendering_and_document_strategy_stop_repeat_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo_with(tmp, {
                "package.json": json.dumps({"dependencies": {"next": "15", "mongoose": "*"}}),
                "next.config.js": "module.exports = {}",
                "requirements.json": json.dumps({
                    "rendering_mode": "ssr",
                    "document_database_strategy": "keep_existing",
                }),
            })
            contract, _, _, _, _, _ = contract_for(root, "requirements.json")
            answered = {x["key"] for x in contract["user_requirements"]}
            missing = {x["key"] for x in contract["unknowns"]}
            self.assertIn("rendering_mode", answered)
            self.assertIn("document_database_strategy", answered)
            self.assertNotIn("rendering_mode", missing)
            self.assertNotIn("document_database_strategy", missing)

    def test_pipeline_emits_questions_and_evidence_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=repo_with(Path(tmp)/"repo",{
                "Dockerfile":"FROM python:3.12",
                ".architecture/requirements.json":json.dumps({
                    "peak_rps":200,"average_rps":20,
                    "region":"ap-northeast-2","requires_authentication":False
                }),
            })
            output=Path(tmp)/"output"
            result=run(root,output,requirements_file=".architecture/requirements.json")
            for file in ("evidence-contract.json","evidence-report.md",
                         "requirements-gaps.json","recommendation.md"):
                self.assertTrue((output/file).is_file(),file)
            c=json.loads((output/"evidence-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(result["evidence_contract"]["explicit_requirements"],4)
            self.assertNotIn("average_rps",{x["key"] for x in c["unknowns"]})
            self.assertEqual(result["questions"],c["questions"])
            self.assertIn("13. 코드 관찰 사실과 추가 요구사항",
                          (output/"recommendation.md").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
