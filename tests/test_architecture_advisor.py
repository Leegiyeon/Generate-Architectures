"""실제 파일 기반 설계 결정과 안전한 요구사항 검증을 확인합니다."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.architecture_advisor import decide, markdown_report


class AdvisorTests(unittest.TestCase):
    def make_repo(self, base, files):
        root = Path(base)
        for name, value in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        return root

    def test_nextjs_unconfirmed_ssr_avoids_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "package.json": json.dumps({"dependencies": {"next": "15.0.0", "pg": "*"}}),
                "src/app/api/users/route.ts": "export async function GET() {}",
            })
            profile = inspect_repository(root)
            result = decide(profile, parse_requirements(None, root))
            self.assertTrue(profile["signals"]["api_routes"])
            self.assertTrue(profile["signals"]["relational_database"])
            self.assertEqual(result["option_id"], "containers")
            self.assertFalse(next(x for x in result["decision"]["alternatives"] if x["id"] == "static")["applicable"])
            self.assertIn("Well-Architected", markdown_report(result))

    def test_explicit_static_next_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "package.json": json.dumps({"dependencies": {"next": "15"}}),
                "next.config.mjs": "export default {output: 'export'};",
            })
            profile = inspect_repository(root)
            self.assertTrue(profile["signals"]["next_static_export"])
            self.assertEqual(decide(profile, parse_requirements(None, root))["option_id"], "static")

    def test_vite_static_and_requirements_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "vite.config.ts": "export default {}",
                "requirements.json": json.dumps({
                    "workload": "web", "deployment_preference": "containers",
                    "monthly_budget_usd": 200, "environment": "production",
                    "requires_authentication": True
                }),
            })
            result = decide(inspect_repository(root), parse_requirements("requirements.json", root))
            self.assertEqual(result["option_id"], "containers")
            self.assertEqual(result["input_budget_usd_month"], 200)
            self.assertEqual(len(result["well_architected_review"]), 6)
            self.assertTrue(any("보안" in x["pillar"] for x in result["well_architected_review"]))

    def test_incompatible_static_preference_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "Dockerfile": "FROM python:3.12",
                "requirements.json": json.dumps({"deployment_preference": "static",
                                                  "requires_relational_database": True}),
            })
            result = decide(inspect_repository(root), parse_requirements("requirements.json", root))
            self.assertEqual(result["option_id"], "containers")
            self.assertTrue(result["decision"]["warnings"])

    def test_mongodb_is_not_mistaken_for_relational_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "Dockerfile": "FROM node:22",
                "package.json": json.dumps({"dependencies": {"mongoose": "*"}}),
            })
            profile = inspect_repository(root)
            self.assertFalse(profile["signals"]["relational_database"])
            self.assertTrue(profile["signals"]["document_database"])
            result = decide(profile, parse_requirements(None, root))
            self.assertEqual(result["option_id"], "containers")
            self.assertNotIn("Amazon RDS", result["nodes"])

    def test_unknown_database_not_drawn_as_real_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {"Dockerfile": "FROM python:3.12"})
            result = decide(inspect_repository(root), parse_requirements(None, root))
            self.assertNotIn("Amazon RDS", result["nodes"])

    def test_api_route_prevents_static(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "vite.config.ts": "export default {}",
                "src/api/users.ts": "export const handler = 1",
            })
            profile = inspect_repository(root)
            self.assertTrue(profile["signals"]["api_routes"])
            self.assertFalse(profile["static_candidate"])

    def test_reject_unknown_and_secret_shaped_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {"requirements.json": '{"aws_secret_access_key": "bad"}'})
            with self.assertRaisesRegex(ValueError, "지원하지 않는"):
                parse_requirements("requirements.json", root)
            with self.assertRaisesRegex(ValueError, "내부"):
                parse_requirements("../outside.json", root)

    def test_deps_are_not_echoed_to_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_repo(tmp, {
                "package.json": json.dumps({"dependencies": {"pg": "1.0.0"}}),
                ".env": "AWS_SECRET_ACCESS_KEY=SHOULD_NOT_LEAK",
            })
            profile = inspect_repository(root)
            self.assertTrue(profile["signals"]["relational_database"])
            self.assertNotIn("SHOULD_NOT_LEAK", json.dumps(profile))


if __name__ == "__main__":
    unittest.main()
