"""Repository graphs retain static import evidence without executing source."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.repository_structure import analyze, analyze_json


class RepositoryStructureTests(unittest.TestCase):
    def report(self, files, root="."):
        return analyze({"root": root, "files": [dict(path=path, after=text, warnings=[])
                                                for path, text in files.items()]})

    def test_absolute_imports_and_explicit_package_targets_keep_lines(self):
        report = self.report({"app/main.py": "import app.models as models\nfrom app import routes\nimport app.models\n",
                              "app/models.py": "", "app/__init__.py": "", "app/routes.py": ""})
        self.assertEqual([(edge["target"], edge["evidence"]["line"]) for edge in report["edges"]],
                         [("app/models.py", 1), ("app/__init__.py", 2), ("app/models.py", 3)])
        self.assertTrue(all(edge["source"] == "app/main.py" and edge["kind"] == "imports"
                            for edge in report["edges"]))
        self.assertEqual(len(report["nodes"]), 4)
        self.assertEqual(report["parsed_files"], 4)
        self.assertFalse(report["unresolved"])

    def test_explicit_source_root_and_relative_imports_do_not_guess_other_roots(self):
        files = {"backend/app/api/routes.py": "from ..models import Item\nfrom . import helpers\nfrom ...outside import nope\n",
                 "backend/app/models.py": "", "backend/app/api/__init__.py": "",
                 "app/models.py": "import os\n"}
        report = self.report(files, root="backend")
        self.assertEqual({edge["target"] for edge in report["edges"]},
                         {"backend/app/models.py", "backend/app/api/__init__.py"})
        self.assertEqual(report["python_files"], 3)
        self.assertEqual(len(report["unresolved"]), 1)
        self.assertIn("루트를 벗어남", report["unresolved"][0]["reason"])
        no_root = self.report({"backend/main.py": "import app.models\n", "backend/app/models.py": ""})
        self.assertFalse(no_root["edges"])

    def test_ambiguous_or_unreadable_targets_are_not_connected(self):
        report = self.report({"main.py": "import app\nimport broken\nimport absent\n",
                              "app.py": "", "app/__init__.py": "", "broken.py": None})
        self.assertFalse(report["edges"])
        self.assertEqual(len(report["unresolved"]), 3)
        self.assertIn("여러 파일", report["unresolved"][0]["reason"])
        self.assertIn("읽지 못해", report["unresolved"][1]["reason"])
        self.assertEqual(report["unreadable_paths"], ["broken.py"])

    def test_direct_imports_require_every_explicit_parent_to_be_a_readable_package(self):
        cases = (
            ({"pkg.py": ""}, "일반 모듈"),
            ({"pkg.py": "", "pkg/__init__.py": ""}, "여러 파일"),
            ({"pkg/__init__.py": None}, "읽지 못"),
            ({"pkg/__init__.py": "def ("}, "읽지 못"),
            ({"pkg/__init__.py": "", "pkg/nested.py": ""}, "일반 모듈"),
            ({"pkg/__init__.py": "", "pkg/nested.py": "", "pkg/nested/__init__.py": ""}, "여러 파일"),
            ({"pkg/__init__.py": "", "pkg/nested/__init__.py": None}, "읽지 못"),
        )
        for parents, reason in cases:
            with self.subTest(parents=parents):
                report = self.report({"main.py": "import pkg.nested.child\n", "pkg/nested/child.py": "", **parents})
                self.assertFalse(report["edges"])
                self.assertEqual(len(report["unresolved"]), 1)
                self.assertEqual(report["unresolved"][0]["path"], "main.py")
                self.assertEqual(report["unresolved"][0]["line"], 1)
                self.assertIn(reason, report["unresolved"][0]["reason"])

    def test_relative_imports_apply_parent_checks_under_the_selected_source_root(self):
        for parents in ({"backend/app/pkg.py": ""},
                        {"backend/app/pkg.py": "", "backend/app/pkg/__init__.py": ""},
                        {"backend/app/pkg/__init__.py": None}):
            with self.subTest(parents=parents):
                report = self.report({"backend/app/main.py": "from .pkg.child import Item\n",
                                      "backend/app/pkg/child.py": "", "backend/app/__init__.py": "", **parents}, root="backend")
                self.assertFalse(report["edges"])
                self.assertEqual(len(report["unresolved"]), 1)
                self.assertIn("상위", report["unresolved"][0]["reason"])

    def test_namespace_package_prefixes_are_allowed_without_inventing_initializers(self):
        report = self.report({"backend/main.py": "import pkg.nested.child\n",
                              "backend/pkg/nested/current.py": "from .child import Item\n",
                              "backend/pkg/nested/child.py": ""}, root="backend")
        self.assertEqual([(edge["source"], edge["target"]) for edge in report["edges"]],
                         [("backend/main.py", "backend/pkg/nested/child.py"),
                          ("backend/pkg/nested/current.py", "backend/pkg/nested/child.py")])
        self.assertFalse(report["unresolved"])

    def test_known_paths_retain_unread_source_candidates_and_cannot_hide_actual_files(self):
        report = analyze({"files": [{"path": "main.py", "after": "import target\n"},
                                    {"path": "target.py", "after": ""}],
                          "known_paths": ["target/__init__.py", "target/__init__.py"]})
        self.assertFalse(report["edges"])
        self.assertEqual(len(report["unresolved"]), 1)
        self.assertIn("여러 파일", report["unresolved"][0]["reason"])
        self.assertEqual(report["parsed_files"], 2)
        self.assertEqual(report["python_files"], 2)
        self.assertEqual(len(report["nodes"]), 2)

    def test_known_only_package_initializer_blocks_descendant_resolution(self):
        report = analyze({"files": [{"path": "main.py", "after": "import pkg.child\n"},
                                    {"path": "pkg/child.py", "after": ""}],
                          "known_paths": ["pkg/__init__.py"]})
        self.assertFalse(report["edges"])
        self.assertIn("상위 패키지 소스를 읽지 못", report["unresolved"][0]["reason"])
        self.assertEqual(report["unreadable_paths"], [])
        self.assertEqual(report["parsed_files"], 2)

    def test_known_only_symlink_or_uncollected_target_is_not_a_graph_node(self):
        report = analyze({"files": [{"path": "main.py", "after": "import target\n"}],
                          "known_paths": ["main.py", "target.py"]})
        self.assertFalse(report["edges"])
        self.assertIn("대상 파일 소스를 읽지 못", report["unresolved"][0]["reason"])
        self.assertEqual([node["path"] for node in report["nodes"]], ["main.py"])
        self.assertEqual(report["python_files"], 1)

    def test_known_paths_validation_is_bounded_and_respects_source_root(self):
        source = [{"path": "backend/main.py", "after": "import target\n"},
                  {"path": "backend/target.py", "after": ""}]
        report = analyze({"root": "backend", "files": source,
                          "known_paths": ["target/__init__.py", "backend/README.md", "backend/target.py"]})
        self.assertEqual([edge["target"] for edge in report["edges"]], ["backend/target.py"])
        for known in (None, "main.py", ["../main.py"], ["a" * 1001 + ".py"], ["main.py"] * 100001):
            with self.subTest(known_type=type(known).__name__), self.assertRaises(ValueError):
                analyze({"files": source, "known_paths": known})

    def test_conditional_nested_external_and_dynamic_imports_stay_unconfirmed(self):
        report = self.report({"main.py": "import os\nif enabled:\n    import service\ndef load():\n    from service import Item\n__import__('service')\n",
                              "service.py": ""})
        self.assertFalse(report["edges"])
        self.assertEqual({entry["line"] for entry in report["unresolved"]}, {1, 3, 5, 6})
        self.assertEqual(len(report["unresolved"]), 4)
        reasons = {entry["line"]: entry["reason"] for entry in report["unresolved"]}
        self.assertIn("외부 패키지", reasons[1])
        self.assertIn("내부 import", reasons[3])
        self.assertIn("내부 import", reasons[5])
        self.assertIn("동적 import 형태", reasons[6])

    def test_route_and_table_declarations_reuse_existing_static_analysis(self):
        source = '''from fastapi import APIRouter
from sqlmodel import SQLModel
router = APIRouter()
@router.get("/items")
def items(): return []
class Item(SQLModel, table=True):
    id: int
def factory():
    inner = APIRouter()
    @inner.delete("/{id}")
    def delete(id): pass
    return inner
'''
        report = self.report({"app.py": source})
        node = report["nodes"][0]
        declarations = node["declarations"]
        self.assertEqual({item["label"] for item in declarations}, {"GET /items", "DELETE /{id}", "Item"})
        self.assertEqual(next(item for item in declarations if item["label"] == "GET /items")["line"], 4)
        self.assertIn("호출 여부 미확인", next(item for item in declarations if item["label"].startswith("DELETE"))["detail"])
        self.assertIn("라우트 선언 2개", node["detail"])
        self.assertIn("테이블 선언 1개", node["detail"])

    def test_route_uncertainty_is_reported_instead_of_a_fabricated_declaration(self):
        report = self.report({"app.py": 'from fastapi import APIRouter\nrouter = APIRouter(prefix=setting)\n@router.get("/items")\ndef items(): pass\n'})
        self.assertFalse(report["nodes"][0]["declarations"])
        self.assertTrue(any("라우터 접두어" in warning for warning in report["warnings"]))

    def test_invalid_paths_roots_and_duplicates_are_rejected(self):
        for path in ("../app.py", "/app.py", "app//a.py", "app/./a.py", "C:/app.py", "app\\a.py", "a\0.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.report({path: ""})
        for root in ("../backend", "/backend", "backend/..", "C:/", "a\\b", "a\0"):
            with self.subTest(root=root), self.assertRaises(ValueError):
                self.report({"app.py": ""}, root=root)
        with self.assertRaisesRegex(ValueError, "중복"):
            analyze({"files": [{"path": "app.py", "after": ""}, {"path": "app.py", "after": ""}]})

    def test_failed_syntax_large_files_and_non_python_do_not_become_valid_nodes(self):
        report = self.report({"invalid.py": "def (", "large.py": "#" * 65537,
                              "missing.py": None, "readme.md": "not Python", "empty.py": ""})
        self.assertEqual(report["python_files"], 4)
        self.assertEqual(report["parsed_files"], 1)
        self.assertEqual([item["path"] for item in report["nodes"]], ["empty.py"])
        self.assertEqual(report["unreadable_paths"], ["invalid.py", "large.py", "missing.py"])

    def test_node_file_edge_and_unresolved_limits_have_exact_omission_counts(self):
        files = {f"module{index:03}.py": "import module000\n" + "import external\n" * 2 for index in range(105)}
        report = self.report(files)
        self.assertEqual(report["python_files"], 105)
        self.assertEqual(report["parsed_files"], 100)
        self.assertEqual(len(report["nodes"]), 80)
        self.assertEqual(report["omitted_nodes"], 20)
        self.assertEqual(len(report["edges"]), 79)
        self.assertEqual(report["omitted_edges"], 20)
        self.assertEqual(len(report["unresolved"]), 100)
        self.assertEqual(report["omitted_unresolved"], 100)
        self.assertEqual(len(report["unreadable_paths"]), 5)
        self.assertTrue(all(edge["source"] in {node["id"] for node in report["nodes"]} for edge in report["edges"]))

    def test_edge_display_limit_retains_distinct_import_evidence_and_exact_omissions(self):
        report = self.report({"source.py": "import target\n" * 450, "target.py": ""})
        self.assertEqual(len(report["edges"]), 400)
        self.assertEqual(report["omitted_edges"], 50)
        self.assertEqual([edge["evidence"]["line"] for edge in report["edges"]], list(range(1, 401)))

    def test_dynamic_import_aliases_are_only_unconfirmed_syntax_candidates(self):
        report = self.report({"main.py": "import importlib as lib\nfrom importlib import import_module as load\nlib.import_module('target')\nload('target')\n",
                              "target.py": ""})
        self.assertFalse(report["edges"])
        self.assertEqual([entry["line"] for entry in report["unresolved"]], [1, 2, 3, 4])
        self.assertTrue(all("동적 import 형태" in entry["reason"] for entry in report["unresolved"][2:]))

    def test_invalid_payload_and_warning_display_limit_are_explicit(self):
        with self.assertRaises(ValueError):
            analyze([])
        report = analyze({"files": [{"path": "empty.py", "after": "",
                                     "warnings": [f"warning {index:03}" for index in range(250)]}]})
        self.assertEqual(len(report["warnings"]), 200)
        self.assertIn("추가 경고 51개", report["warnings"][-1])

    def test_declaration_limit_preserves_actual_counts(self):
        source = "from sqlmodel import SQLModel\n" + "\n".join(
            f"class Model{index:02}(SQLModel, table=True):\n    id: int\n" for index in range(25))
        node = self.report({"models.py": source})["nodes"][0]
        self.assertEqual(len(node["declarations"]), 20)
        self.assertEqual(node["omitted_declarations"], 5)
        self.assertIn("테이블 선언 25개", node["detail"])

    def test_source_is_never_executed_and_json_wrapper_retains_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist"
            source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise RuntimeError('no')\n"
            report = json.loads(analyze_json(json.dumps({"files": [{"path": "앱.py", "after": source}]})))
            self.assertFalse(marker.exists())
            self.assertEqual(report["parsed_files"], 1)
            self.assertEqual(report["nodes"][0]["label"], "앱.py")


if __name__ == "__main__":
    unittest.main()
