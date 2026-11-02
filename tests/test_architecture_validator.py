"""정적 Architecture Validator 회귀 테스트: 충돌/미측정/오판 방지."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.architecture_advisor import decide
from scripts.architecture_validator import (
    validate_architecture, markdown_validation, markdown_adr,
)
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run


def fixture(files=None, req=None):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for name, value in (files or {"Dockerfile": "FROM python:3.12"}).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    requirements = parse_requirements(None, root)
    requirements.update(req or {})
    profile = inspect_repository(root)
    proposal = decide(profile, requirements)
    return temp, profile, requirements, proposal


def validate(profile, requirements, architecture, graph=None):
    return validate_architecture(architecture, profile, requirements, graph)


class ArchitectureValidatorTests(unittest.TestCase):
    def test_basic_draft_never_claims_pass(self):
        tmp, p, r, a = fixture()
        try:
            v = validate(p, r, a)
            self.assertEqual(v["decision_gate"], "review_required")
            for key in ("production_ready", "aws_account_checked", "cost_estimated",
                        "performance_tested", "security_compliance_verified",
                        "ai_proposal_applied"):
                self.assertIs(v[key], False)
            self.assertEqual(len(v["well_architected"]), 6)
            self.assertTrue(all(x["status"] == "검증 전" for x in v["well_architected"]))
            self.assertFalse(any(x["severity"] == "blocker" for x in v["findings"]))
        finally:
            tmp.cleanup()

    def test_conflicting_relational_and_persistence_inputs_block(self):
        tmp, p, r, a = fixture(req={
            "requires_relational_database": True,
            "requires_persistent_storage": False,
        })
        try:
            v = validate(p, r, a)
            self.assertEqual(v["decision_gate"], "blocked")
            self.assertIn("REQ-001", {f["rule_id"] for f in v["findings"]})
            self.assertFalse(v["production_ready"])
            self.assertIn("운영 적합성", markdown_validation(v))
        finally:
            tmp.cleanup()

    def test_static_with_api_or_db_is_blocked(self):
        tmp, p, r, a = fixture(files={"vite.config.ts": "export default {}"},
                                req={"requires_persistent_storage": True})
        try:
            a["option_id"] = "static"
            v = validate(p, r, a)
            self.assertIn("PAT-003", {f["rule_id"] for f in v["findings"]})
            p["signals"]["api_routes"] = True
            v2 = validate(p, r, a)
            self.assertIn("PAT-001", {f["rule_id"] for f in v2["findings"]})
        finally:
            tmp.cleanup()

    def test_unverified_nextjs_ssr_blocks_static(self):
        tmp, p, r, a = fixture(files={
            "next.config.js": "module.exports = {}",
            "package.json": json.dumps({"dependencies": {"next": "*"}}),
        })
        try:
            a["option_id"] = "static"
            v = validate(p, r, a)
            self.assertIn("PAT-002", {f["rule_id"] for f in v["findings"]})
        finally:
            tmp.cleanup()

    def test_serverless_relational_and_mobile_wrong_workload_block(self):
        tmp, p, r, a = fixture(req={"requires_relational_database": True, "workload": "web"})
        try:
            a["option_id"] = "serverless"
            self.assertIn("PAT-004", {x["rule_id"] for x in validate(p, r, a)["findings"]})
            a["option_id"] = "mobile"
            self.assertIn("PAT-005", {x["rule_id"] for x in validate(p, r, a)["findings"]})
        finally:
            tmp.cleanup()

    def test_invalid_unknown_node_or_edge_block(self):
        tmp, p, r, a = fixture()
        try:
            a["nodes"].append("MadeUpDatabase")
            a["edges"].append(("MadeUpDatabase", "NotPresent"))
            v = validate(p, r, a)
            self.assertEqual(v["decision_gate"], "blocked")
            self.assertTrue({"ARC-004", "ARC-005", "ARC-006"}.issubset(
                {f["rule_id"] for f in v["findings"]}))
        finally:
            tmp.cleanup()

    def test_explicit_sensitive_production_targets_require_evidence(self):
        tmp, p, r, a = fixture(req={
            "environment": "production", "data_classification": "sensitive",
            "requires_authentication": True, "availability_target_percent": 99.95,
            "rto_minutes": 30, "rpo_minutes": 5,
            "expected_monthly_requests": 1000000,
            "monthly_budget_usd": 500,
        })
        try:
            v = validate(p, r, a)
            rules = {x["rule_id"] for x in v["findings"]}
            self.assertTrue({"SEC-001", "SEC-003", "REL-001", "REL-002",
                             "OPS-001", "PERF-001", "COST-001"}.issubset(rules))
            self.assertFalse(v["production_ready"])
        finally:
            tmp.cleanup()

    def test_incomplete_parser_is_not_treated_as_absent(self):
        tmp, p, r, a = fixture()
        try:
            v = validate(p, r, a, {"errors": [{"path": "a.ts"}], "scan_truncated": True})
            self.assertIn("EVD-001", {x["rule_id"] for x in v["findings"]})
            self.assertEqual(v["decision_gate"], "review_required")
        finally:
            tmp.cleanup()

    def test_ai_proposal_does_not_change_choice_or_gate(self):
        tmp, p, r, a = fixture()
        try:
            original = a["option_id"]
            v = validate_architecture(a, p, r, ai_review={
                "status": "reviewed_unverified",
                "review": {"recommended_option": "static"},
            })
            self.assertEqual(a["option_id"], original)
            self.assertFalse(v["ai_proposal_applied"])
            self.assertEqual(v["ai_review_status"], "reviewed_unverified")
            self.assertNotIn("승인 완료", markdown_adr(a, v))
        finally:
            tmp.cleanup()

    def test_end_to_end_writes_validation_adr_and_korean_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            (root / "Dockerfile").write_text("FROM python:3.12")
            out = Path(tmp) / "artifact"
            result = run(root, out)
            self.assertEqual(result["validation"]["decision_gate"], "review_required")
            for filename in ("validation.json", "validation.md", "decision-record.md"):
                self.assertTrue((out / filename).is_file())
            snapshot = json.loads((out / "validation.json").read_text(encoding="utf-8"))
            self.assertFalse(snapshot["aws_account_checked"])
            summary = (out / "recommendation.md").read_text(encoding="utf-8")
            self.assertIn("정적 제약 검토", summary)
            self.assertIn("승인 전", (out / "decision-record.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
