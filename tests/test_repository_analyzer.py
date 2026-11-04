"""파일 경로 단서에서 테스트를 API로 오인하지 않는지 검증합니다."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.repository_analyzer import inspect_repository


class RepositoryAnalyzerTests(unittest.TestCase):
    def inspect(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            return inspect_repository(root)

    def test_api_evidence_excludes_test_files_and_fixture_directories(self):
        runtime_paths = [
            "src/app/api/game/route.ts", "pages/api/users.js",
            "src/api/test.ts", "src/api/spec.ts", "src/api/testimonials.py",
            "src/api/load_test.ts", "src/api/test_endpoint.go",
            "app/health/route.js",
            "app/api/test/route.ts", "src/app/api/tests/route.ts",
            "src/app/fixtures/route.js",
        ]
        test_paths = [
            "src/app/api/game/route.test.ts", "src/api/users.spec.tsx",
            "src/api/test_users.py", "src/api/users_test.py", "src/api/users_test.go",
            "tests/app/api/game/route.ts", "test/api/users.js",
            "src/api/__tests__/users.ts", "src/api/__mocks__/users.js",
            "fixtures/app/api/users/route.ts", "src/api/__fixtures__/users.py",
            "src/app/api/__tests__/route.ts",
        ]
        profile = self.inspect(dict.fromkeys(runtime_paths + test_paths, ""))
        self.assertEqual(profile["evidence"]["api_routes"], sorted(runtime_paths))
        self.assertTrue(profile["signals"]["api_routes"])

    def test_test_only_api_paths_do_not_block_static_candidate(self):
        profile = self.inspect({
            "package.json": json.dumps({"devDependencies": {"vite": "*"}}),
            "src/api/users.test.ts": "export function test() {}",
            "fixtures/api/users.ts": "export function handler() {}",
        })
        self.assertEqual(profile["evidence"]["api_routes"], [])
        self.assertFalse(profile["signals"]["api_routes"])
        self.assertTrue(profile["static_candidate"])

    def test_custom_auth_remains_unconfirmed_and_explicitly_asks_for_review(self):
        profile = self.inspect({
            "package.json": "{}",
            "src/lib/admin-auth.ts": "export function verifySession() {}",
        })
        self.assertFalse(profile["signals"]["authentication_library"])
        self.assertEqual(profile["evidence"]["auth_dependencies"], [])
        self.assertTrue(any("자체 구현" in question for question in profile["questions"]))
        self.assertTrue(any("인증 부재" in limitation for limitation in profile["limitations"]))

    def test_known_auth_dependency_is_still_detected(self):
        profile = self.inspect({
            "package.json": json.dumps({"dependencies": {"next-auth": "*"}}),
        })
        self.assertTrue(profile["signals"]["authentication_library"])
        self.assertEqual(profile["evidence"]["auth_dependencies"], ["next-auth"])


if __name__ == "__main__":
    unittest.main()
