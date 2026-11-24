"""Factory route summaries retain static binding and source evidence limits."""
import unittest

from scripts.pr_preview_browser import analyze


class FactoryRoutePreviewTests(unittest.TestCase):
    def compare(self, before, after):
        return analyze({"files": [{"path": "app/routes.py", "before": before, "after": after}]})

    def assert_unresolved_change(self, before):
        report = self.compare(before, before.replace("return []", "return [1]"))
        self.assert_review_candidate(report)

    def assert_review_candidate(self, report):
        self.assertEqual(report["routes"], [])
        reasons = "\n".join(reason for _, entries in report["review"] for reason in entries)
        self.assertIn("자동 라우트 비교 범위 밖", reasons)
        self.assertIn("handler", reasons)

    def test_request_argument_change_in_direct_factory_handler(self):
        before = '''from fastapi import APIRouter, Request
def get_users_router():
    router = APIRouter(prefix="/users")
    @router.delete("/{id}")
    async def delete_user(user):
        await manager.delete(user)
    return router
'''
        after = before.replace("delete_user(user)", "delete_user(request: Request, user)").replace(
            "manager.delete(user)", "manager.delete(user, request=request)")
        report = self.compare(before, after)
        self.assertTrue(any("DELETE /users/{id}" in entry and "함수 get_users_router" in entry
                            and "app/routes.py:4" in entry for entry in report["routes"]))
        self.assertTrue(any("인자 추가" in entry and "request: Request" in entry
                            for entry in report["routes"]))
        self.assertFalse(any("get_users_router.delete_user" in reason
                             for _, entries in report["review"] for reason in entries))

    def test_same_path_in_other_factory_does_not_appear_changed(self):
        before = '''from fastapi import FastAPI
def first_factory():
    app = FastAPI()
    @app.get("/health")
    def health(): return "first"
    return app
def second_factory():
    app = FastAPI()
    @app.get("/health")
    def health(): return "second"
    return app
'''
        report = self.compare(before, before.replace('return "second"', 'return "updated"'))
        changes = [entry for entry in report["routes"] if "GET /health" in entry]
        self.assertEqual(len(changes), 1)
        self.assertIn("함수 second_factory", changes[0])
        self.assertNotIn("first_factory", changes[0])

    def test_global_and_local_constructor_and_module_aliases(self):
        for module_import, local_import, constructor in (
            ("from fastapi import APIRouter as Router\n", "", "Router"),
            ("import fastapi as fa\n", "", "fa.FastAPI"),
            ("", "    from fastapi import APIRouter as Router\n", "Router"),
            ("", "    import fastapi as fa\n", "fa.FastAPI"),
        ):
            with self.subTest(constructor=constructor, local=bool(local_import)):
                before = (module_import + "def factory():\n" + local_import
                          + f"    router = {constructor}()\n"
                          + '    @router.get("/items")\n'
                          + "    def handler(): return []\n    return router\n")
                report = self.compare(before, before.replace("return []", "return [1]"))
                self.assertTrue(any("GET /items" in entry and "함수 factory" in entry
                                    for entry in report["routes"]))

    def test_function_parameters_shadow_global_import_aliases(self):
        for module_import, argument, constructor in (
            ("from fastapi import APIRouter\n", "APIRouter", "APIRouter"),
            ("import fastapi as fa\n", "fa", "fa.APIRouter"),
        ):
            with self.subTest(argument=argument):
                before = (module_import + f"def factory({argument}):\n"
                          + f"    router = {constructor}()\n"
                          + '    @router.get("/items")\n'
                          + "    def handler(): return []\n    return router\n")
                self.assert_unresolved_change(before)
                resolved = before.replace(f"def factory({argument}):", "def factory():")
                self.assert_review_candidate(self.compare(resolved, before))
                self.assert_review_candidate(self.compare(before, resolved))

    def test_rebinding_or_nonunique_imports_do_not_verify_routes(self):
        for module_import, setup in (
            ("from fastapi import APIRouter\n", "    APIRouter = custom_router\n"),
            ("import fastapi as fa\n", "    fa = custom_module\n"),
            ("from fastapi import APIRouter\nAPIRouter = custom_router\n", ""),
            ("import fastapi as fa\nfa = custom_module\n", ""),
            ("from fastapi import APIRouter\n", "    router = custom_router\n"),
        ):
            with self.subTest(module_import=module_import, setup=setup):
                constructor = "fa.APIRouter" if "import fastapi as fa" in module_import else "APIRouter"
                before = (module_import + "def factory():\n"
                          + f"    router = {constructor}()\n" + setup
                          + '    @router.get("/items")\n'
                          + "    def handler(): return []\n    return router\n")
                self.assert_unresolved_change(before)

    def test_conditional_receivers_and_handlers_stay_review_candidates(self):
        resolved = ('from fastapi import APIRouter\ndef factory():\n'
                    '    router = APIRouter()\n    @router.get("/items")\n'
                    '    def handler(): return []\n')
        for body in (
            '    if enabled:\n        router = APIRouter()\n'
            '    @router.get("/items")\n    def handler(): return []\n',
            '    router = APIRouter()\n    if enabled:\n'
            '        @router.get("/items")\n        def handler(): return []\n',
        ):
            with self.subTest(body=body):
                conditional = "from fastapi import APIRouter\ndef factory():\n" + body
                self.assert_unresolved_change(conditional)
                self.assert_review_candidate(self.compare(resolved, conditional))
                self.assert_review_candidate(self.compare(conditional, resolved))

    def test_dynamic_prefixes_and_paths_stay_review_candidates(self):
        for constructor, route_path in (("APIRouter(prefix=prefix)", '"/items"'),
                                        ("APIRouter()", "route_path")):
            with self.subTest(constructor=constructor, route_path=route_path):
                before = ("from fastapi import APIRouter\ndef factory():\n"
                          + f"    router = {constructor}\n    @router.get({route_path})\n"
                          + "    def handler(): return []\n    return router\n")
                self.assert_unresolved_change(before)
                resolved = before.replace("APIRouter(prefix=prefix)", "APIRouter()").replace(
                    "@router.get(route_path)", '@router.get("/items")')
                self.assert_review_candidate(self.compare(resolved, before))
                self.assert_review_candidate(self.compare(before, resolved))

    def test_deleted_factory_route_uses_previous_commit_evidence(self):
        before = '''from fastapi import APIRouter
def factory():
    router = APIRouter()
    @router.get("/removed")
    def handler(): return []
    return router
'''
        report = self.compare(before, "")
        changes = [entry for entry in report["routes"] if "GET /removed" in entry]
        self.assertEqual(len(changes), 1)
        self.assertIn("삭제", changes[0])
        self.assertIn("함수 factory", changes[0])
        self.assertIn("app/routes.py:4 (이전 커밋)", changes[0])

    def test_nested_default_assignment_shadows_global_and_local_imports(self):
        for module_import, local_import in (
            ("from fastapi import APIRouter\n", ""),
            ("", "    from fastapi import APIRouter\n"),
        ):
            with self.subTest(local_import=bool(local_import)):
                before = (module_import + "def factory():\n" + local_import
                          + "    def helper(arg=(APIRouter := OtherRouter)):\n        pass\n"
                          + "    router = APIRouter()\n"
                          + '    @router.get("/items")\n'
                          + "    def handler(): return []\n    return router\n")
                self.assert_unresolved_change(before)
                resolved = before.replace(
                    "    def helper(arg=(APIRouter := OtherRouter)):\n        pass\n", "")
                self.assert_review_candidate(self.compare(resolved, before))
                self.assert_review_candidate(self.compare(before, resolved))

    def test_factory_scope_label_cannot_overwrite_literal_module_route(self):
        before = '''from fastapi import FastAPI, APIRouter
app = FastAPI()
@app.get("/items (함수 factory)")
def module_handler(): return "old"
def factory():
    router = APIRouter()
    @router.get("/items")
    def handler(): return []
    return router
'''
        report = self.compare(before, before.replace('return "old"', 'return "new"'))
        changes = [entry for entry in report["routes"] if "GET /items" in entry]
        self.assertEqual(len(changes), 1)
        self.assertIn("GET /items (함수 factory)", changes[0])
        self.assertIn("app/routes.py:3", changes[0])


if __name__ == "__main__":
    unittest.main()
