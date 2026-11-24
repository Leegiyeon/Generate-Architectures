"""Alembic alter_column summaries preserve declarations without inferring DB state."""
import textwrap
import unittest

from scripts.pr_preview_browser import analyze


class AlterColumnPreviewTests(unittest.TestCase):
    path = "alembic/versions/change_columns.py"

    def source(self, body, imports="from alembic import op\nimport sqlalchemy as sa\n"):
        return imports + "def upgrade():\n" + textwrap.indent(body, "    ") + "\n"

    def migrations(self, after, before=""):
        return analyze({"files": [{"path": self.path, "before": before, "after": after}]})["migrations"]

    def test_type_expression_and_existing_type_are_distinct_declarations(self):
        changes = self.migrations(self.source(
            'op.alter_column("user", "email", existing_type=sa.String(), '
            'type_=sa.String(length=255), existing_nullable=False)'
        ))
        self.assertEqual(len(changes), 1)
        summary = changes[0]
        self.assertIn("user.email", summary)
        self.assertIn("sa.String(length=255)", summary)
        self.assertIn("기존 타입 선언", summary)
        self.assertIn("sa.String()", summary)
        self.assertNotIn("NULL 불허", summary)
        self.assertIn(f"{self.path}:4", summary)
        expression = self.migrations(self.source('op.alter_column("user", "email", type_=build_type())'))
        self.assertEqual(len(expression), 1)
        self.assertIn("타입 선언", expression[0])
        self.assertIn("build_type()", expression[0])

    def test_explicit_nullable_overrides_existing_nullable_metadata(self):
        for value, label, other in ((True, "NULL 허용", "NULL 불허"), (False, "NULL 불허", "NULL 허용")):
            with self.subTest(nullable=value):
                changes = self.migrations(self.source(
                    f'op.alter_column("user", "email", nullable={value}, existing_nullable={not value})'
                ))
                self.assertEqual(len(changes), 1)
                self.assertIn(label, changes[0])
                self.assertNotIn(other, changes[0])

    def test_server_default_removal_expression_and_false_sentinel(self):
        cases = (
            ("None", "server_default 제거"),
            ('sa.text("now()")', "server_default 선언"),
            ("False", None),
        )
        for expression, label in cases:
            with self.subTest(server_default=expression):
                changes = self.migrations(self.source(
                    f'op.alter_column("user", "created_at", server_default={expression})'
                ))
                if label is None:
                    self.assertEqual(changes, [])
                else:
                    self.assertEqual(len(changes), 1)
                    self.assertIn(label, changes[0])
                    if expression != "None":
                        self.assertIn("now()", changes[0])
                        self.assertNotIn("server_default 제거", changes[0])

    def test_import_alias_schema_and_literal_new_column_name(self):
        changes = self.migrations(self.source(
            'migration.alter_column("user", "email", schema="accounts", new_column_name="contact_email")',
            imports="from alembic import op as migration\n",
        ))
        self.assertEqual(len(changes), 1)
        self.assertIn("accounts.user.email", changes[0])
        self.assertIn("contact_email", changes[0])

    def test_existing_metadata_only_is_not_a_schema_change(self):
        for arguments in (
            "existing_nullable=False",
            "existing_type=sa.String(length=255)",
            'existing_server_default=sa.text("now()")',
            "existing_type=sa.String(), existing_nullable=False, server_default=False",
            "type_=None, nullable=None, new_column_name=None",
            "nullable=desired_nullable",
        ):
            with self.subTest(arguments=arguments):
                changes = self.migrations(self.source(f'op.alter_column("user", "email", {arguments})'))
                self.assertEqual(changes, [])

    def test_dynamic_and_indirect_operations_do_not_create_evidence(self):
        bodies = (
            'op.alter_column(table_name, "email", nullable=False)',
            'op.alter_column("user", column_name, nullable=False)',
            'op.alter_column("user", "email", schema=schema_name, nullable=False)',
            'op.alter_column("user", "email", new_column_name=new_name, nullable=False)',
            'op.alter_column("user", "email", **options)',
            'if enabled:\n    op.alter_column("user", "email", nullable=False)',
            'def helper():\n    op.alter_column("user", "email", nullable=False)\nhelper()',
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.migrations(self.source(body)), [])
        downgrade = (
            "from alembic import op\ndef upgrade():\n    pass\n"
            'def downgrade():\n    op.alter_column("user", "email", nullable=False)\n'
        )
        self.assertEqual(self.migrations(downgrade), [])

    def test_shadowed_or_ambiguous_op_import_does_not_create_evidence(self):
        sources = (
            self.source('op = other\nop.alter_column("user", "email", nullable=False)'),
            self.source('op.alter_column("user", "email", nullable=False)',
                        imports="from alembic import op\nfrom unrelated import op\n"),
            'from alembic import op\ndef upgrade(op):\n    op.alter_column("user", "email", nullable=False)\n',
        )
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(self.migrations(source), [])

    def test_removed_declaration_uses_previous_line_and_moved_declaration_is_unchanged(self):
        source = self.source('op.alter_column("user", "email", type_=sa.String(length=255))')
        removed = self.migrations("", before=source)
        self.assertEqual(len(removed), 1)
        self.assertIn("삭제", removed[0])
        self.assertIn(f"{self.path}:4", removed[0])
        self.assertIn("(이전 커밋)", removed[0])
        self.assertEqual(self.migrations("\n\n" + source, before=source), [])


if __name__ == "__main__":
    unittest.main()
