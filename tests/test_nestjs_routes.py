"""Import-backed NestJS route syntax, without executing the target application."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.application_graph import build_application_graph
from scripts.recommend_architecture import run


class NestJSRouteTests(unittest.TestCase):
    def graph(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "controller.ts").write_text(source, encoding="utf-8")
            graph = build_application_graph(root)
            self.assertFalse(graph["errors"], graph["errors"])
            return graph

    @staticmethod
    def routes(graph):
        return {node["name"] for node in graph["nodes"] if node["type"] == "route"}

    def test_starter_root_handler_has_evidence_and_handles_edge_without_invented_di(self):
        graph = self.graph("""import { Controller, Get } from '@nestjs/common';
import { AppService } from './app.service';
@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}
  @Get()
  getHello(): string { return this.appService.getHello(); }
}
""")
        self.assertEqual(self.routes(graph), {"GET /"})
        route = next(node for node in graph["nodes"] if node["type"] == "route")
        self.assertEqual(route["evidence"], {"path": "controller.ts", "line": 6, "origin": "ast"})
        self.assertTrue(any(edge["source"] == route["id"] and edge["type"] == "handles" and
                            edge["target"] == "function:controller.ts:AppController.getHello"
                            for edge in graph["edges"]))
        self.assertFalse(any(edge["type"] == "calls" for edge in graph["edges"]))

    def test_named_aliases_and_literal_prefixes_and_http_methods(self):
        graph = self.graph("""import { Controller as C, Get as Read, Post, Put, Patch, Delete, Options, Head } from '@nestjs/common';
@C('/cats/')
export class CatsController {
 @Read('/:id/') findOne() {}
 @Post() create() {}
 @Put(':id') replace() {}
 @Patch(':id') patch() {}
 @Delete(':id') remove() {}
 @Options() options() {}
 @Head('') head() {}
}
@C('dogs')
export class DogsController { @Read() all() {} }
""")
        self.assertEqual(self.routes(graph), {"GET /cats/:id", "POST /cats", "PUT /cats/:id",
                                             "PATCH /cats/:id", "DELETE /cats/:id",
                                             "OPTIONS /cats", "HEAD /cats", "GET /dogs"})

    def test_unrelated_decorators_and_missing_controller_are_not_routes(self):
        for source in (
            "import { Controller, Get } from './local'; @Controller() class Local { @Get() list() {} }",
            "import { Get } from '@nestjs/common'; class Service { @Get('hidden') list() {} }",
            "import type { Controller, Get } from '@nestjs/common'; @Controller() class Types { @Get() list() {} }",
            "@Controller() class Unbound { @Get() list() {} }",
        ):
            with self.subTest(source=source):
                self.assertEqual(self.routes(self.graph(source)), set())

    def test_dynamic_controller_and_handler_paths_are_unresolved_without_values(self):
        graph = self.graph("""import { Controller, Get } from '@nestjs/common';
const secret = 'DO_NOT_DISCLOSE';
@Controller(secret)
class DynamicController { @Get('visible') list() {} }
@Controller('cats')
class CatsController {
 @Get(secret) dynamic() {}
 @Get(['one', 'two']) multiple() {}
 @Get() known() {}
}
@Controller({path: 'dogs'})
class OptionsController { @Get() list() {} }
""")
        self.assertEqual(self.routes(graph), {"GET /cats"})
        self.assertEqual(len(graph["unresolved_routes"]), 4)
        self.assertNotIn("DO_NOT_DISCLOSE", json.dumps(graph))
        self.assertTrue(all(item["path"] == "controller.ts" and item["line"] > 0
                            for item in graph["unresolved_routes"]))

    def test_nested_shadowed_binding_does_not_create_a_controller(self):
        graph = self.graph("""import { Controller, Get } from '@nestjs/common';
function local(Controller, Get) {
 @Controller('not-nest') class Nested { @Get() list() {} }
}
""")
        self.assertEqual(self.routes(graph), set())

    def test_multiple_http_decorators_and_static_method_are_not_resolved(self):
        graph = self.graph("""import { Controller, Get, Post } from '@nestjs/common';
@Controller('cats') class Cats {
 @Get() @Post() ambiguous() {}
 @Get() static utility() {}
}
""")
        self.assertEqual(self.routes(graph), set())
        self.assertEqual(len(graph["unresolved_routes"]), 2)

    def test_two_handlers_on_one_line_remain_distinct_routes(self):
        graph = self.graph("import {Controller, Get} from '@nestjs/common'; "
                           "@Controller('cats') class Cats { @Get('one') one() {} @Get('two') two() {} }")
        self.assertEqual(self.routes(graph), {"GET /cats/one", "GET /cats/two"})
        self.assertEqual(sum(edge["type"] == "handles" for edge in graph["edges"]), 2)

    def test_full_pipeline_uses_ast_route_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            root.mkdir()
            (root / "package.json").write_text(json.dumps({"dependencies": {
                "@nestjs/common": "*", "@nestjs/core": "*"}}), encoding="utf-8")
            (root / "controller.ts").write_text(
                "import {Controller, Get} from '@nestjs/common';\n"
                "@Controller() export class App { @Get() home() { return 'hello'; } }\n",
                encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                run(root, Path(temporary) / "report")
            profile = json.loads((Path(temporary) / "report/repository-analysis.json").read_text())
            self.assertTrue(profile["signals"]["api_routes"])
            self.assertFalse(profile["static_candidate"])
            self.assertEqual(profile["evidence"]["ast_api_routes"][0]["route"], "GET /")


if __name__ == "__main__":
    unittest.main()
