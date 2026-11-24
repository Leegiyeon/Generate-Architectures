"""Static browser snapshot comparisons must preserve source evidence and gaps."""
import json
import unittest

from scripts.pr_preview_browser import analyze, analyze_json
from scripts.preview_fastapi_pr import MAX_SOURCE_BYTES


class BrowserPreviewTests(unittest.TestCase):
    def test_routes_models_dtos_and_migration_evidence(self):
        old = '''from fastapi import APIRouter
from sqlmodel import SQLModel
router = APIRouter()
class Account(SQLModel, table=True):
    id: int
class AccountPublic(SQLModel):
    id: int
@router.get("/accounts", response_model=list[AccountPublic])
def accounts():
    return []
'''
        new = old.replace("    id: int", "    id: int\n    label: str").replace("return []", "return query.order_by(Account.id)")
        migration = '''from alembic import op
import sqlalchemy as sa
def upgrade():
    op.add_column("account", sa.Column("label", sa.String(), nullable=True))
'''
        report = json.loads(analyze_json(json.dumps({"files": [
            {"path": "app/models.py", "before": old, "after": new},
            {"path": "alembic/versions/add_label.py", "before": "", "after": migration},
        ]})))
        self.assertEqual(report["parsed_files"], 2)
        self.assertTrue(any("GET /accounts" in entry and "app/models.py:" in entry for entry in report["routes"]))
        self.assertTrue(any("order_by" in entry for entry in report["routes"]))
        self.assertTrue(any("Account.label" in entry for entry in report["models"]))
        self.assertTrue(any("AccountPublic.label" in entry for entry in report["responses"]))
        self.assertFalse(any("AccountPublic" in entry for entry in report["models"]))
        self.assertTrue(any("account.label" in entry and "NULL 허용" in entry for entry in report["migrations"]))

    def test_custom_selectors_and_path_scope(self):
        source = "class Custom:\n    id: int\n"
        report = analyze({"files": [
            {"path": "app/custom.py", "before": source, "after": source + "    name: str\n"},
            {"path": "other/routes.py", "before": None, "after": None},
        ], "paths": ["app/"], "models": ["app/custom.py:Custom"],
            "responses": ["app/custom.py:Custom", "app/custom.py:Missing"]})
        self.assertEqual(report["changed_files"], 1)
        self.assertTrue(any("Custom.name" in entry for entry in report["models"]))
        self.assertTrue(any("Custom.name" in entry for entry in report["responses"]))
        self.assertTrue(any("Missing" in reason for _, reasons in report["review"] for reason in reasons))

    def test_partial_or_unparseable_sources_never_invent_changes(self):
        source = 'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): return 1\n'
        for before in (None, "def broken(", "#" * (MAX_SOURCE_BYTES + 1)):
            with self.subTest(before=type(before).__name__):
                report = analyze({"files": [{"path": "api.py", "before": before, "after": source}]})
                self.assertEqual(report["routes"], [])
                self.assertEqual(report["parsed_files"], 0)
                self.assertTrue(report["review"][0][1])

    def test_removed_source_uses_previous_commit_evidence(self):
        report = analyze({"files": [{"path": "models.py", "before":
            "from sqlmodel import SQLModel\nclass Item(SQLModel, table=True):\n    id: int\n", "after": ""}]})
        self.assertTrue(all("(이전 커밋)" in entry for entry in report["models"]))
        self.assertTrue(report["models"])

    def test_invalid_custom_selector_is_reported(self):
        with self.assertRaises(ValueError):
            analyze({"files": [], "models": ["not-a-model"]})

    def test_field_constraint_expressions_are_visible_without_execution(self):
        before = 'from sqlmodel import SQLModel, Field\nclass Item(SQLModel, table=True):\n    title: str\n'
        after = before.replace('title: str', 'title: str = Field(min_length=1, max_length=255)')
        report = analyze({"files": [{"path": "models.py", "before": before, "after": after}]})
        self.assertIn("  필드 선언값 · Item.title · 지정 없음 → Field(min_length=1, max_length=255)", report["models"])
        self.assertTrue(any("models.py:3" in item for item in report["models"]))

    def test_unresolved_module_route_is_not_reported_as_added_or_deleted(self):
        resolved = ('from fastapi import APIRouter\nrouter = APIRouter(prefix="/api")\n'
                    '@router.get("/items")\ndef handler(): return []\n')
        dynamic = resolved.replace('"/api"', 'configured_prefix')
        for before, after in ((resolved, dynamic), (dynamic, resolved)):
            with self.subTest(before=before):
                report = analyze({"files": [{"path": "api.py", "before": before, "after": after}]})
                self.assertEqual(report['routes'], [])
                self.assertTrue(any('자동 라우트 비교 범위 밖' in reason
                                    for _, reasons in report['review'] for reason in reasons))

    def test_changed_factory_route_has_source_and_argument_evidence(self):
        before = '''from fastapi import APIRouter, Request
def get_users_router():
    router = APIRouter()
    @router.delete("/{id}")
    async def delete_user(user):
        await manager.delete(user)
    @router.get("/me")
    async def me():
        return user
    return router
'''
        after = before.replace("delete_user(user)", "delete_user(request: Request, user)").replace(
            "manager.delete(user)", "manager.delete(user, request=request)")
        report = analyze({"files": [{"path": "router/users.py", "before": before, "after": after}]})
        self.assertTrue(any("DELETE /{id}" in entry and "함수 get_users_router" in entry
                            and "router/users.py:4" in entry for entry in report["routes"]))
        self.assertIn("  인자 추가 · request: Request", report["routes"])
        self.assertFalse(any("GET /me" in entry for entry in report["routes"]))
        reasons = "\n".join(report["review"][0][1])
        self.assertNotIn("자동 라우트 비교 범위 밖", reasons)
        self.assertNotIn("단서 없음", reasons)

    def test_deleted_nested_candidate_points_to_previous_source(self):
        before = '''class Routes:
    @router.get("/old")
    def old(): pass
'''
        report = analyze({"files": [{"path": "router.py", "before": before, "after": ""}]})
        self.assertTrue(any("Routes.old" in reason and "이전 2행" in reason
                            for reason in report["review"][0][1]))

    def test_unchanged_nested_declaration_has_no_change_warning(self):
        before = 'def factory():\n    @router.get("/x")\n    def handler(): return 1\n'
        report = analyze({"files": [{"path": "router.py", "before": before, "after": "\n" + before}]})
        self.assertFalse(any("자동 라우트 비교 범위 밖" in reason for reason in report["review"][0][1]))


if __name__ == "__main__":
    unittest.main()
