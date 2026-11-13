"""Regression coverage for statically resolved FastAPI routes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.application_graph import build_application_graph
from scripts.evidence_contract import build_evidence_contract


class FastAPIRouteTests(unittest.TestCase):
    def graph(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "service.py").write_text(source, encoding="utf-8")
            graph = build_application_graph(root)
        self.assertEqual(graph["errors"], [])
        return graph

    @staticmethod
    def routes(graph):
        return [node for node in graph["nodes"] if node["type"] == "route"]

    def assert_unresolved_routes(self, graph, expected):
        self.assertCountEqual(
            [(item["path"], item["line"], item["reason"]) for item in graph["unresolved_routes"]],
            [("service.py", line, reason) for line, reason in expected],
        )

    def test_import_aliases_produce_local_routes_with_handler_evidence(self):
        graph = self.graph("""from fastapi import FastAPI as Application, APIRouter as Router
import fastapi as fa

web = Application()
admin: fa.FastAPI = fa.FastAPI()
catalog = Router(prefix="/catalog")
audit = fa.APIRouter()

@web.get(path="/health")
async def health():
    return {"ok": True}

@admin.get("/status")
def status():
    return {"ok": True}

@catalog.get("")
def catalog_index():
    return []

@catalog.patch("/{item_id}")
def update_item(item_id: str):
    return {"id": item_id}

@audit.head(path="/recent")
def recent():
    pass
""")
        expected = {
            "GET /health": ("app_local", 9, "health"),
            "GET /status": ("app_local", 13, "status"),
            "GET /catalog": ("router_local", 17, "catalog_index"),
            "PATCH /catalog/{item_id}": ("router_local", 21, "update_item"),
            "HEAD /recent": ("router_local", 25, "recent"),
        }
        routes = self.routes(graph)
        contract = build_evidence_contract({}, graph, {})
        observations = {
            observation["value"]: observation for observation in contract["observations"]
            if observation["category"] == "ast_route"
        }
        self.assertCountEqual([route["name"] for route in routes], expected.keys())
        self.assertEqual(observations.keys(), expected.keys())
        for route in routes:
            with self.subTest(route=route["name"]):
                scope, line, handler = expected[route["name"]]
                evidence = {"path": "service.py", "line": line, "origin": "ast"}
                self.assertEqual(route["route_scope"], scope)
                self.assertEqual(route["evidence"], evidence)
                observation = observations[route["name"]]
                self.assertEqual(observation["route_scope"], scope)
                self.assertEqual(observation["source"], {
                    "path": "service.py", "line": line, "method": "ast",
                })
                self.assertFalse(observation["runtime_verified"])
                if handler in {"catalog_index", "update_item"}:
                    prefix_source = {"path": "service.py", "line": 6}
                    self.assertEqual(route["prefix_source"], prefix_source)
                    self.assertEqual(observation["prefix_source"], prefix_source)
                else:
                    self.assertNotIn("prefix_source", route)
                    self.assertNotIn("prefix_source", observation)
                self.assertIn({
                    "source": route["id"],
                    "target": f"function:service.py:{handler}",
                    "type": "handles",
                    "evidence": evidence,
                }, graph["edges"])
        self.assert_unresolved_routes(graph, [])

    def test_unrelated_and_rebound_bindings_do_not_create_routes(self):
        graph = self.graph("""from fastapi import FastAPI, APIRouter as Router
import fastapi as fa
from local import APIRouter

app = unrelated_service()
router = APIRouter()
api = FastAPI()
api = unrelated_service()
Router = unrelated_factory
resource = Router()
fa = unrelated_module
web = fa.FastAPI()

@app.get("/arbitrary")
def arbitrary():
    pass

@router.get("/lookalike")
def lookalike():
    pass

@api.get("/rebound-receiver")
def rebound_receiver():
    pass

@resource.get("/rebound-constructor")
def rebound_constructor():
    pass

@web.get("/rebound-module")
def rebound_module():
    pass
""")
        self.assertEqual(self.routes(graph), [])

    def test_comprehension_target_is_local_and_later_wildcard_import_is_ambiguous(self):
        graph = self.graph("""from fastapi import FastAPI

service = FastAPI()
names = [service.name for service in services]

@service.get("/before")
def before():
    pass

from other import *

@service.get("/after")
def after():
    pass
""")
        self.assertEqual([route["name"] for route in self.routes(graph)], ["GET /before"])

    def test_dynamic_paths_and_router_prefixes_record_only_static_evidence(self):
        graph = self.graph("""from fastapi import FastAPI, APIRouter

prefix = "/DO_NOT_DISCLOSE_ROUTER_PREFIX"
path = "/DO_NOT_DISCLOSE_HANDLER_PATH"
api = FastAPI()
dynamic_router = APIRouter(prefix=prefix)
known_router = APIRouter(prefix="/known")

@dynamic_router.get("/unresolved")
def dynamic_prefix():
    pass

@api.get(path=path)
def dynamic_app_path():
    pass

@known_router.get(path)
def dynamic_router_path():
    pass

@known_router.get("/items")
def known():
    pass
""")
        self.assertEqual([route["name"] for route in self.routes(graph)], ["GET /known/items"])
        self.assert_unresolved_routes(graph, [
            (9, "fastapi_router_prefix_not_resolved"),
            (13, "fastapi_route_path_not_resolved"),
            (17, "fastapi_route_path_not_resolved"),
        ])
        self.assertNotIn("DO_NOT_DISCLOSE", json.dumps(graph))
        contract = build_evidence_contract({}, graph, {})
        self.assertEqual(contract["status"], "partial")
        self.assertEqual(contract["coverage"]["unresolved_routes"], 3)

    def test_include_router_and_conditional_registrations_keep_local_paths(self):
        graph = self.graph("""from fastapi import FastAPI, APIRouter

service = FastAPI()
router = APIRouter(prefix="/products")
deployment_prefix = "/DO_NOT_DISCLOSE_MOUNT_PREFIX"

@router.get("/search")
def search():
    return []

service.include_router(router, prefix="/v1")
service.include_router(router, prefix=deployment_prefix)

if is_enabled():
    service.include_router(router)

    @service.get("/conditional")
    def conditional():
        pass

def register(service):
    service.include_router(router)
""")
        self.assertEqual([route["name"] for route in self.routes(graph)], ["GET /products/search"])
        self.assert_unresolved_routes(graph, [
            (11, "fastapi_include_not_resolved"),
            (12, "fastapi_include_prefix_not_resolved"),
            (15, "fastapi_conditional_registration"),
            (17, "fastapi_conditional_registration"),
        ])
        self.assertNotIn("DO_NOT_DISCLOSE", json.dumps(graph))

    @unittest.skipUnless(sys.version_info >= (3, 14), "requires Python 3.14 AST grammar")
    def test_route_in_module_using_python_314_exception_syntax(self):
        graph = self.graph("""from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    try:
        return check_status()
    except ValueError, TypeError:
        return {}
""")
        self.assertEqual([route["name"] for route in self.routes(graph)], ["GET /health"])


if __name__ == "__main__":
    unittest.main()
