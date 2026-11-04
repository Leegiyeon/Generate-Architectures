"""의존성 선언과 인프라 경로의 제한된 정적 근거 회귀."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.repository_analyzer import inspect_repository, MAX_BYTES


class PythonDependencyEvidenceTests(unittest.TestCase):
    def inspect(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            return inspect_repository(root)

    def test_pyproject_runtime_dependencies_have_actual_manifest_provenance(self):
        profile = self.inspect({"backend/pyproject.toml": '''
[project]
dependencies = ["FastAPI[standard]>=0.100", "SQLModel>=0.0.20", "psycopg[binary]>=3", "PyJWT>=2"]
'''})
        self.assertIn("FastAPI", profile["technologies"])
        self.assertTrue(profile["signals"]["relational_database"])
        self.assertTrue(profile["signals"]["authentication_library"])
        self.assertEqual(profile["evidence"]["db_dependencies"], ["psycopg", "sqlmodel"])
        self.assertEqual(profile["evidence"]["auth_dependencies"], ["pyjwt"])
        self.assertEqual(profile["evidence"]["database_engine_evidence"], [])
        self.assertEqual(profile["evidence"]["relational_dependency_paths"], ["backend/pyproject.toml"])
        self.assertEqual(profile["evidence"]["auth_dependency_paths"], ["backend/pyproject.toml"])
        self.assertIn({"path": "backend/pyproject.toml", "technology": "FastAPI",
                       "category": "backend"}, profile["manifests"])
        self.assertIn({"name": "psycopg", "path": "backend/pyproject.toml",
                       "ecosystem": "python", "section": "project.dependencies"},
                      profile["evidence"]["dependency_sources"])
        self.assertTrue(any("실제 DB 연결" in value for value in profile["limitations"]))

    def test_requirements_named_specs_do_not_fetch_or_disclose_urls(self):
        profile = self.inspect({"api/requirements.txt": '''
# sqlalchemy, PyJWT are mentioned only in this comment
FastAPI[standard] >= 0.100 # runtime declaration
psycopg2_binary==2.9 ; python_version >= "3.11"
PyJWT @ https://example.invalid/pkg.whl?token=PRIVATE_VALUE
-r nested.txt
--index-url https://example.invalid/PRIVATE_INDEX
sqlmodel unexpected suffix
''', "api/nested.txt": "motor>=3\n"})
        self.assertTrue(profile["signals"]["relational_database"])
        self.assertEqual(profile["evidence"]["db_dependencies"], ["psycopg2-binary"])
        self.assertEqual(profile["evidence"]["auth_dependencies"], ["pyjwt"])
        self.assertFalse(profile["signals"]["document_database"])
        text = json.dumps(profile)
        self.assertNotIn("PRIVATE_VALUE", text)
        self.assertNotIn("PRIVATE_INDEX", text)
        self.assertNotIn("example.invalid", text)

    def test_optional_groups_dynamic_and_tool_tables_do_not_imply_runtime_use(self):
        profile = self.inspect({"pyproject.toml": '''
[project]
name = "sample"
dynamic = ["dependencies"]
[project.optional-dependencies]
db = ["sqlmodel", "psycopg"]
[dependency-groups]
dev = ["pyjwt", "fastapi"]
[tool.poetry.dependencies]
motor = "*"
'''})
        self.assertFalse(profile["signals"]["relational_database"])
        self.assertFalse(profile["signals"]["authentication_library"])
        self.assertFalse(profile["signals"]["document_database"])
        self.assertNotIn("FastAPI", profile["technologies"])
        self.assertEqual(profile["evidence"]["dependency_sources"], [])
        self.assertTrue(any("optional" in text for text in profile["limitations"]))

    def test_invalid_or_wrong_type_pyproject_does_not_create_dependency_signals(self):
        for value in ('[project\ndependencies=["psycopg"]',
                      '[project]\ndependencies="psycopg"',
                      '[project]\ndependencies=["PyJWT", 7]'):
            with self.subTest(value=value):
                profile = self.inspect({"pyproject.toml": value})
                self.assertFalse(profile["signals"]["relational_database"])
                self.assertFalse(profile["signals"]["authentication_library"])

    def test_malformed_pep508_declarations_do_not_create_signals(self):
        for declaration in ("sqlmodel @ --index-url https://example.invalid", "PyJWT @ a b",
                            "sqlmodel[,]", "PyJWT[ , ]", "psycopg ; !!!",
                            'PyJWT; python_version >=', 'fastapi[standard>=1',
                            'psycopg=>3'):
            for filename, text in (
                    ("requirements.txt", declaration),
                    ("pyproject.toml", '[project]\ndependencies=[' + json.dumps(declaration) + ']')):
                with self.subTest(declaration=declaration, filename=filename):
                    profile = self.inspect({filename: text})
                    self.assertFalse(profile["signals"]["relational_database"])
                    self.assertFalse(profile["signals"]["authentication_library"])
                    self.assertNotIn("FastAPI", profile["technologies"])
                    self.assertEqual(profile["evidence"]["dependency_sources"], [])

    def test_oversize_and_symlink_dependency_manifests_are_not_read(self):
        profile = self.inspect({"pyproject.toml": "#" * (MAX_BYTES + 1) + '\n[project]\ndependencies=["psycopg"]'})
        self.assertFalse(profile["signals"]["relational_database"])
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "deps.toml"
            target.write_text('[project]\ndependencies=["psycopg"]')
            (Path(tmp) / "pyproject.toml").symlink_to(target)
            profile = inspect_repository(tmp)
            self.assertFalse(profile["signals"]["relational_database"])
            self.assertEqual(profile["evidence"]["dependency_sources"], [])

    def test_ecosystems_do_not_reinterpret_other_package_names(self):
        profile = self.inspect({
            "package.json": json.dumps({"dependencies": {"sqlmodel": "*", "pyjwt": "*"}}),
            "requirements.txt": "pg\nnext\nvite\n",
        })
        self.assertFalse(profile["signals"]["relational_database"])
        self.assertFalse(profile["signals"]["authentication_library"])
        self.assertFalse(profile["signals"]["nextjs"])
        self.assertNotIn("Vite", profile["technologies"])

    def test_nested_npm_sources_preserve_existing_detection_without_fake_root_paths(self):
        profile = self.inspect({"frontend/package.json": json.dumps({
            "dependencies": {"next": "*", "pg": "*", "next-auth": "*"},
            "devDependencies": {"vite": "*"},
        })})
        self.assertTrue(profile["signals"]["nextjs"])
        self.assertTrue(profile["signals"]["relational_database"])
        self.assertTrue(profile["signals"]["authentication_library"])
        frameworks = [m for m in profile["manifests"] if m["technology"] in ("Next.js", "Vite")]
        self.assertEqual({m["path"] for m in frameworks}, {"frontend/package.json"})
        self.assertEqual(profile["evidence"]["relational_dependency_paths"], ["frontend/package.json"])

    def test_nestjs_core_manifest_points_to_its_declaring_package(self):
        profile = self.inspect({"backend/package.json": json.dumps({
            "dependencies": {"@nestjs/core": "*", "@nestjs/common": "*"},
        })})
        self.assertIn({"path": "backend/package.json", "technology": "NestJS",
                       "category": "backend"}, profile["manifests"])
        self.assertFalse(profile["signals"]["api_routes"])

    def test_nested_container_and_compose_names_are_consistent_evidence(self):
        names = ["services/api/Dockerfile", "ops/compose.yml", "ops/compose.yaml",
                 "ops/docker-compose.yml", "ops/docker-compose.yaml"]
        profile = self.inspect(dict.fromkeys(names, "# static path only"))
        self.assertTrue(profile["signals"]["docker"])
        self.assertEqual(profile["evidence"]["infrastructure_paths"], sorted(names))
        self.assertEqual({m["path"] for m in profile["manifests"]}, set(names))


if __name__ == "__main__":
    unittest.main()
