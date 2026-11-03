"""Issue #12: 서비스 선정 근거·대안·충돌 검증, 비용/AI의 권한 분리."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.architecture_decision_engine import compare_architectures, markdown_decision_matrix
from scripts.architecture_advisor import decide
from scripts.evidence_contract import build_evidence_contract
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run


def case(files, given=None):
    tmp=tempfile.TemporaryDirectory()
    root=Path(tmp.name)
    for name, body in files.items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(body,encoding="utf-8")
    requirements=parse_requirements(None,root)
    req=given or {}
    requirements.update(req)
    profile=inspect_repository(root)
    proposed=decide(profile,requirements)
    evidence=build_evidence_contract(profile,{"nodes":[],"edges":[]},
                                     requirements,req.keys(),proposed)
    return tmp,compare_architectures(proposed,profile,requirements,evidence)


class ArchitectureDecisionTests(unittest.TestCase):
    def test_static_export_has_no_ec2_cost_ranking(self):
        tmp,result=case({"vite.config.ts":"export default {}"})
        try:
            self.assertEqual(result["selected_reference"],"static")
            self.assertEqual(result["status"],"alternatives_need_review")
            self.assertFalse(result["selected_reference_approved"])
            self.assertTrue(all(c["cost_status"]=="not_estimated" for c in result["candidates"]))
            self.assertTrue(all(c["performance_status"]=="not_tested" for c in result["candidates"]))
            self.assertIn("EC2",markdown_decision_matrix(result))
        finally:tmp.cleanup()

    def test_explicit_ssr_blocks_static_only_deployment(self):
        tmp,result=case({
            "package.json":json.dumps({"dependencies":{"next":"15.0.0"}}),
            "next.config.js":"module.exports = {output:'export'}",
        },{"rendering_mode":"ssr"})
        try:
            self.assertEqual(result["selected_reference"],"static")
            self.assertEqual(result["status"],"blocked_for_review")
            static=next(c for c in result["candidates"] if c["id"]=="static")
            self.assertIn("DEC-STATIC-SSR",{r["rule_id"] for r in static["blockers"]})
            self.assertFalse(static["approved"])
        finally:tmp.cleanup()

    def test_long_jobs_block_standard_lambda_without_switching_selection(self):
        tmp,result=case({"pyproject.toml":"[project]\nname='api'\n"},
                        {"max_job_duration_seconds":1800})
        try:
            self.assertEqual(result["selected_reference"],"lambda")
            self.assertEqual(result["status"],"blocked_for_review")
            lam=next(c for c in result["candidates"] if c["id"]=="lambda")
            self.assertIn("DEC-LAMBDA-DURATION",{r["rule_id"] for r in lam["blockers"]})
            self.assertFalse(lam["approved"])
        finally:tmp.cleanup()

    def test_required_host_control_blocks_lambda_and_fargate_but_keeps_ec2_as_review_option(self):
        tmp,result=case({"Dockerfile":"FROM python:3.12"},
                        {"requires_host_control":True})
        try:
            fargate=next(c for c in result["candidates"] if c["id"]=="fargate")
            lam=next(c for c in result["candidates"] if c["id"]=="lambda")
            ec2=next(c for c in result["candidates"] if c["id"]=="ec2")
            self.assertEqual(result["selected_reference"],"fargate")
            self.assertEqual(result["status"],"blocked_for_review")
            self.assertIn("DEC-FARGATE-HOST",{x["rule_id"] for x in fargate["blockers"]})
            self.assertIn("DEC-LAMBDA-HOST",{x["rule_id"] for x in lam["blockers"]})
            self.assertFalse(ec2["blockers"])
            self.assertEqual(ec2["status"],"review_required")
            self.assertIn("ec2",result["alternative_candidates"])
        finally:tmp.cleanup()

    def test_relational_database_blocks_current_lambda_template_only(self):
        tmp,result=case({"Dockerfile":"FROM python:3.12",
                         "package.json":json.dumps({"dependencies":{"pg":"*"}})})
        try:
            fargate=next(c for c in result["candidates"] if c["id"]=="fargate")
            lam=next(c for c in result["candidates"] if c["id"]=="lambda")
            self.assertEqual(result["selected_reference"],"fargate")
            self.assertFalse(fargate["blockers"])
            self.assertIn("DEC-LAMBDA-RDS-TEMPLATE",{r["rule_id"] for r in lam["blockers"]})
        finally:tmp.cleanup()

    def test_reproducible_without_llm_or_external_api(self):
        tmp,result=case({"Dockerfile":"FROM python:3.12"},
                        {"peak_rps":100,"operations_preference":"minimize_maintenance"})
        try:
            root=Path(tmp.name)
            req=parse_requirements(None,root)
            req.update({"peak_rps":100,"operations_preference":"minimize_maintenance"})
            profile=inspect_repository(root)
            a=decide(profile,req)
            c=build_evidence_contract(profile,{"nodes":[],"edges":[]},req,
                                      ("peak_rps","operations_preference"),a)
            later=compare_architectures(a,profile,req,c)
            self.assertEqual(result,later)
            self.assertFalse(any(x["approved"] for x in result["candidates"]))
            self.assertTrue(all(c["cost_status"] == "not_estimated"
                                for c in later["candidates"]))
            self.assertFalse(any(x["rule_id"] == "DEC-COST-UNVERIFIED"
                                 for c in later["candidates"]
                                 for x in c["review_required"]))
        finally:tmp.cleanup()

    def test_full_pipeline_uses_human_approval_gate_without_auto_changed_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            (root/"requirements.json").write_text(json.dumps({
                "requires_host_control":True,
                "max_job_duration_seconds":3600,
                "region":"ap-northeast-2",
            }),encoding="utf-8")
            output=Path(tmp)/"output"
            result=run(root,output,requirements_file="requirements.json")
            self.assertEqual(result["option_id"],"containers")
            self.assertEqual(result["decision_matrix"]["status"],"blocked_for_review")
            self.assertEqual(result["validation"]["decision_gate"],"blocked")
            matrix=json.loads((output/"architecture-decision-matrix.json").read_text(encoding="utf-8"))
            self.assertFalse(matrix["selected_reference_approved"])
            self.assertIn("ec2",matrix["alternative_candidates"])
            self.assertTrue((output/"architecture-decision-matrix.md").is_file())
            self.assertIn("15. AWS 서비스별 선정·제외 근거",
                          (output/"recommendation.md").read_text(encoding="utf-8"))
            self.assertTrue((output/"architecture.svg").is_file())

    def test_invalid_host_boolean_and_job_duration_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"requirements.json"
            for entry in ({"requires_host_control":"true"},
                          {"max_job_duration_seconds":0},
                          {"max_job_duration_seconds":604801}):
                file.write_text(json.dumps(entry),encoding="utf-8")
                with self.assertRaises(ValueError):
                    parse_requirements("requirements.json",tmp)


if __name__=="__main__":
    unittest.main()
