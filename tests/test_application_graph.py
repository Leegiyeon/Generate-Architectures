"""AST application graph regression tests (no executing untrusted repository code)."""
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from scripts.application_graph import build_application_graph
from scripts.render_application_graph import render_application_diagram
from scripts.recommend_architecture import run


class ApplicationGraphTests(unittest.TestCase):
    def test_rendered_node_name_and_source_are_on_separate_lines(self):
        graph = {"nodes": [{"id": "function:fetch_user", "type": "function",
                             "name": "fetch_user", "path": "app/service.py", "line": 7}],
                 "edges": []}
        with tempfile.TemporaryDirectory() as tmp:
            render_application_diagram(graph, tmp)
            root = ElementTree.parse(Path(tmp) / "application-graph.svg").getroot()
            ns = {"svg": "http://www.w3.org/2000/svg"}
            node = next(group for group in root.findall(".//svg:g", ns)
                        if group.attrib.get("class") == "node")
            labels = node.findall("svg:text", ns)
            self.assertEqual([label.text for label in labels], ["fetch_user", "app/service.py:7"])
            self.assertGreater(float(labels[1].attrib["y"]), float(labels[0].attrib["y"]))

    @staticmethod
    def repo(root, files):
        root=Path(root)
        for filename,content in files.items():
            path=root/filename
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding="utf-8")
        return root

    def test_python_fastapi_service_route_call_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.repo(tmp,{
                "app/__init__.py":"",
                "app/main.py": "from fastapi import FastAPI\nfrom .service import fetch_user\napp = FastAPI()\n@app.get('/users/{id}')\ndef users(id):\n    return fetch_user(id)\n",
                "app/service.py":"def fetch_user(id):\n    return id\n",
                "app/models.py":"class Base: pass\nclass User(Base):\n    pass\n",
            })
            graph=build_application_graph(root)
            node={n["id"]:n for n in graph["nodes"]}
            edges={(e["source"],e["target"],e["type"]) for e in graph["edges"]}
            self.assertIn("route:app/main.py:4:GET",node)
            self.assertIn("model:app/models.py:User",node)
            self.assertIn(("route:app/main.py:4:GET","function:app/main.py:users","handles"),edges)
            self.assertIn(("function:app/main.py:users","function:app/service.py:fetch_user","calls"),edges)
            self.assertTrue(all(e["evidence"]["path"] for e in graph["edges"]))

    def test_typescript_next_api_import_and_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.repo(tmp,{
                "src/app/api/users/route.ts":'import { listUsers } from "../../../services/users";\nexport async function GET() { return listUsers(); }\n',
                "src/services/users.ts":'export function listUsers(): string[] { return []; }\n'
            })
            graph=build_application_graph(root)
            node={n["id"]:n for n in graph["nodes"]}
            edges={(e["source"],e["target"],e["type"]) for e in graph["edges"]}
            self.assertFalse(graph["errors"],graph["errors"])
            self.assertIn("route:src/app/api/users/route.ts:2:GET",node)
            # service path is resolved only when import spec actually points to a local module
            self.assertIn("function:src/services/users.ts:listUsers",node)
            self.assertIn(("function:src/app/api/users/route.ts:GET","function:src/services/users.ts:listUsers","calls"),edges)

    def test_express_and_prisma_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.repo(tmp,{
                "src/server.js":'const router = require("express").Router();\nfunction ping(req,res){res.send("ok")}\nrouter.get("/ping", ping);\n',
                "prisma/schema.prisma":'datasource db { provider = "postgresql" }\nmodel Person {\n id Int @id\n}\n'
            })
            graph=build_application_graph(root)
            types={n["name"] for n in graph["nodes"] if n["type"] in {"route","model"}}
            self.assertIn("GET /ping",types)
            self.assertIn("Person",types)

    def test_test_handlers_do_not_become_ast_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            python_handler = 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/test-only")\ndef handler(): return {}\n'
            root = self.repo(tmp, {
                "src/api/test_users.py": python_handler,
                "src/api/users_test.py": python_handler,
                "src/api/__fixtures__/users.py": python_handler,
                "src/app/api/users/route.test.ts": 'export function GET() { return {}; }\n',
                "src/app/api/users/route.spec.ts": 'export function POST() { return {}; }\n',
                "src/api/test.py": 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/runtime")\ndef runtime(): return {}\n',
                "src/app/api/users/route.ts": 'export function GET() { return {}; }\n',
                "src/app/api/test/route.ts": 'export function GET() { return {}; }\n',
                "src/app/api/__tests__/route.ts": 'export function GET() { return {}; }\n',
            })
            graph = build_application_graph(root)
            self.assertFalse(graph["errors"], graph["errors"])
            module_paths = {node["path"] for node in graph["nodes"] if node["type"] == "module"}
            self.assertEqual(module_paths, {"src/api/test.py", "src/app/api/users/route.ts",
                                            "src/app/api/test/route.ts"})
            route_paths = {node["path"] for node in graph["nodes"] if node["type"] == "route"}
            self.assertEqual(route_paths, module_paths)

    def test_no_invented_calls_and_no_secret_disclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.repo(tmp,{
                "app/main.py": 'from requests import get\ndef main():\n    return get("https://example.org/?token=PRIVATE_VALUE")\n',
                ".env":"SECRET=DO_NOT_SHOW",
                "tests/test_app.py":'def internal(): return "DO_NOT_SHOW"'
            })
            graph=build_application_graph(root)
            self.assertNotIn("DO_NOT_SHOW",json.dumps(graph))
            self.assertNotIn("PRIVATE_VALUE",json.dumps(graph))
            self.assertEqual(graph["counts"]["edges"].get("calls",0),0)

    def test_end_to_end_writes_both_types_of_diagram(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.repo(Path(tmp)/"repo",{
                "Dockerfile":"FROM python:3.12",
                "app.py":'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): return {"ok":True}\n'
            })
            out=Path(tmp)/"output"
            result=run(root,out)
            self.assertEqual(result["application_graph"]["nodes"].get("route"),1)
            for name in ("application-graph.svg","application-graph.png","application-graph.json",
                         "architecture.svg","recommendation.md"):
                self.assertTrue((out/name).is_file(),name)
            self.assertIn("코드 기반 애플리케이션 그래프",(out/"recommendation.md").read_text(encoding="utf-8"))
            self.assertTrue((out/"application-graph.png").read_bytes().startswith(bytes([137,80,78,71])))
            self.assertIn('application-graph.json',(out/"recommendation.md").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
