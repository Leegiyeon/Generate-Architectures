"""PR structure diagrams retain declaration evidence and snapshot boundaries."""
import ast
import unittest

from scripts.pr_preview_structure import MAX_STRUCTURE_NODES, structure_snapshots


class StructureSnapshotTests(unittest.TestCase):
    def snapshots(self, before, after, models=None, responses=None, path="app/models.py"):
        return structure_snapshots([(path, [ast.parse(before), ast.parse(after)], [])],
                                   models or {}, responses or {})

    def declaration(self, graph, label):
        return next(item for item in graph["nodes"] if item["label"] == label)

    def test_route_and_model_changes_keep_source_lines_and_declaration_edges(self):
        before = '''from fastapi import APIRouter
from sqlmodel import SQLModel
router = APIRouter()
class Item(SQLModel, table=True):
    id: int
@router.get("/items")
def items():
    return []
'''
        after = before.replace("    id: int", "    id: int\n    title: str").replace("return []", "return [1]")
        report = self.snapshots(before, after)
        for graph in (report["before"], report["after"]):
            self.assertEqual(len(graph["nodes"]), 3)
            self.assertEqual(len(graph["edges"]), 2)
            self.assertTrue(all(item["kind"] == "defines" for item in graph["edges"]))
            self.assertTrue(all(item["status"] == "modified" for item in graph["nodes"]))
            for edge in graph["edges"]:
                child = next(item for item in graph["nodes"] if item["id"] == edge["target"])
                self.assertEqual(edge["evidence"], {"path": child["path"], "line": child["line"]})
        self.assertEqual(self.declaration(report["before"], "GET /items")["line"], 6)
        self.assertEqual(self.declaration(report["after"], "GET /items")["line"], 7)
        self.assertIn("title: str", self.declaration(report["after"], "Item")["detail"])

    def test_added_removed_and_moved_declarations_have_stable_status(self):
        before = 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/old")\ndef old(): pass\n'
        after = before.replace('"/old"', '"/new"').replace("def old", "def new")
        changes = self.snapshots(before, after)
        self.assertEqual(self.declaration(changes["before"], "GET /old")["status"], "removed")
        self.assertEqual(self.declaration(changes["after"], "GET /new")["status"], "added")
        moved = self.snapshots(before, "\n\n" + before)
        self.assertTrue(all(item["status"] == "unchanged" for graph in (moved["before"], moved["after"])
                            for item in graph["nodes"]))
        self.assertEqual(self.declaration(moved["after"], "GET /old")["line"], 5)

    def test_unreadable_side_is_not_a_deletion_or_addition_and_non_python_is_ignored(self):
        tree = ast.parse('from sqlmodel import SQLModel\nclass Item(SQLModel, table=True):\n    id: int\n')
        report = structure_snapshots([("models.py", [tree], ["이전 소스를 읽지 못함"]),
                                      ("README.md", [], [])], {}, {})
        self.assertEqual(report["unreadable_paths"], ["models.py"])
        self.assertEqual(report["before"]["nodes"], [])
        self.assertEqual(report["after"]["nodes"], [])

    def test_factory_routes_preserve_uncertainty_and_duplicate_registrations(self):
        source = '''from fastapi import APIRouter
def router_factory():
    router = APIRouter()
    @router.get("/items")
    def first(): pass
    @router.get("/items")
    def second(): pass
    return router
'''
        report = self.snapshots(source, source)
        routes = [item for item in report["after"]["nodes"] if item["kind"] == "route"]
        self.assertEqual(len(routes), 2)
        self.assertNotEqual(routes[0]["id"], routes[1]["id"])
        self.assertTrue(all("함수 router_factory 내부 · 호출 여부 미확인" in item["detail"] for item in routes))
        self.assertEqual({item["line"] for item in routes}, {4, 6})

    def test_selected_classes_and_model_precedence_keep_only_direct_fields(self):
        source = '''from sqlmodel import SQLModel
class Parent(SQLModel):
    inherited: str
class Item(Parent, table=True):
    id: int
class Public(SQLModel):
    title: str
class Custom:
    custom: str
'''
        selected = {"app/models.py": {"Item", "Custom"}}
        responses = {"app/models.py": {"Item", "Public", "Absent"}}
        report = self.snapshots(source, source, selected, responses)
        nodes = report["after"]["nodes"]
        self.assertEqual({item["label"] for item in nodes}, {"app/models.py", "Item", "Custom", "Public"})
        item = self.declaration(report["after"], "Item")
        self.assertEqual(item["kind"], "model")
        self.assertIn("id: int", item["detail"])
        self.assertNotIn("inherited", item["detail"])
        self.assertEqual(self.declaration(report["after"], "Public")["kind"], "response")

    def test_node_limit_counts_omissions_without_changing_full_snapshot_status(self):
        source = "from sqlmodel import SQLModel\n" + "\n".join(
            f"class Model{index:03}(SQLModel, table=True):\n    id: int\n" for index in range(85))
        after = source + "\nclass Last(SQLModel, table=True):\n    id: int\n"
        report = self.snapshots(source, after)
        for side, omitted in (("before", 6), ("after", 7)):
            graph = report[side]
            self.assertEqual(len(graph["nodes"]), MAX_STRUCTURE_NODES)
            self.assertEqual(graph["nodes"][0]["kind"], "file")
            self.assertEqual(graph["omitted_nodes"], omitted)
            self.assertTrue(all(item["status"] == "unchanged" for item in graph["nodes"]
                                if item["kind"] == "model" and item["label"] != "Last"))
            ids = {item["id"] for item in graph["nodes"]}
            self.assertTrue(all(item["source"] in ids and item["target"] in ids for item in graph["edges"]))

    def test_direct_field_detail_is_bounded_and_empty_side_has_no_file(self):
        source = "from sqlmodel import SQLModel\nclass Item(SQLModel, table=True):\n" + "".join(
            f"    field{index}: str\n" for index in range(10))
        report = self.snapshots("", source)
        self.assertEqual(report["before"]["nodes"], [])
        self.assertTrue(all(item["status"] == "added" for item in report["after"]["nodes"]))
        detail = self.declaration(report["after"], "Item")["detail"]
        self.assertIn("field7: str", detail)
        self.assertNotIn("field8: str", detail)
        self.assertIn("외 2개", detail)

    def test_sources_are_never_executed_and_no_calls_or_db_edges_are_inferred(self):
        source = '''from sqlmodel import SQLModel
raise RuntimeError("Source must not be executed")
class Item(SQLModel, table=True):
    id: int
def handler():
    return session.query(Item)
'''
        report = self.snapshots(source, source)
        self.assertEqual({item["kind"] for item in report["after"]["nodes"]}, {"file", "model"})
        self.assertEqual([item["kind"] for item in report["after"]["edges"]], ["defines"])

    def test_unresolved_transition_is_not_a_route_addition_or_deletion(self):
        resolved = ('from fastapi import APIRouter\nrouter = APIRouter(prefix="/api")\n'
                    '@router.get("/items")\ndef handler(): return []\n')
        for unresolved in (resolved.replace('"/api"', 'configured_prefix'),
                           resolved.replace('@router.get("/items")', '@router.get(configured_path)'),
                           resolved.replace('APIRouter(prefix="/api")', 'make_router()')):
            for before, after in ((resolved, unresolved), (unresolved, resolved)):
                with self.subTest(before=before):
                    graph = self.snapshots(before, after)
                    self.assertTrue(all(node['kind'] != 'route' for side in ('before', 'after')
                                        for node in graph[side]['nodes']))
                    self.assertEqual(graph['uncertain_route_paths'], ['app/models.py'])


if __name__ == "__main__":
    unittest.main()
