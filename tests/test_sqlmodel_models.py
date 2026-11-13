"""Regression coverage for static SQLModel table declarations."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.application_graph import build_application_graph
from scripts.evidence_contract import build_evidence_contract


class SQLModelDeclarationTests(unittest.TestCase):
    def graph(self, files):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, source in files.items():
                (root / name).write_text(source, encoding="utf-8")
            graph = build_application_graph(root)
        self.assertEqual(graph["errors"], [])
        return graph

    def test_table_declarations_appear_with_source_evidence(self):
        graph = self.graph({
            "models.py": """from sqlmodel import SQLModel as Record, Field
import sqlmodel as sm

class Account(Record, table=True):
    __tablename__ = "DO_NOT_DISCLOSE_TABLE"
    owner: int = Field(foreign_key="DO_NOT_DISCLOSE_REFERENCE")

class Base(sm.SQLModel):
    label: str

class Item(Base, table=True):
    id: int

class ItemResponse(Base):
    id: int

class ItemRequest(Record):
    label: str
""",
            "legacy.py": "class Base: pass\nclass Existing(Base): pass\n",
        })
        contract = build_evidence_contract({}, graph, {})
        models = {node["name"]: node for node in graph["nodes"] if node["type"] == "model"}
        observations = {
            item["value"]: item for item in contract["observations"]
            if item["category"] == "ast_model"
        }
        self.assertEqual(set(models), {"Account", "Item", "Existing"})
        self.assertEqual(set(observations), set(models))
        self.assertNotIn("model_kind", models["Existing"])
        self.assertNotIn("model_kind", observations["Existing"])
        for name, line in (("Account", 4), ("Item", 11)):
            with self.subTest(model=name):
                node = models[name]
                self.assertEqual(node["model_kind"], "sqlmodel_table")
                source = {"path": "models.py", "line": line}
                evidence = {**source, "origin": "ast"}
                self.assertEqual(node["evidence"], evidence)
                self.assertIn({
                    "source": "file:models.py", "target": node["id"],
                    "type": "defines", "evidence": evidence,
                }, graph["edges"])
                observation = observations[name]
                self.assertEqual(observation["model_kind"], "sqlmodel_table")
                self.assertEqual(observation["source"], {**source, "method": "ast"})
                self.assertFalse(observation["runtime_verified"])
        self.assertNotIn("DO_NOT_DISCLOSE", json.dumps((graph, contract)))

    def test_ambiguous_declarations_do_not_become_table_models(self):
        graph = self.graph({
            "options.py": """from sqlmodel import SQLModel

table_mode = True
class NotATable(SQLModel, table=False): pass
class Dynamic(SQLModel, table=table_mode): pass
class IntegerFlag(SQLModel, table=1): pass
class StringFlag(SQLModel, table="true"): pass

class Unrelated: pass
class Lookalike(Unrelated, table=True): pass

if table_mode:
    class Conditional(SQLModel, table=True): pass

class Replaced(SQLModel, table=True): pass
Replaced = Unrelated

class Shared(SQLModel): pass
Shared = Unrelated
class ViaReplacedBase(Shared, table=True): pass
""",
            "imports.py": """from sqlmodel import SQLModel as Record
import sqlmodel as sm

from app_types import SQLModel
Record = SQLModel
sm = other_module
class SameName(SQLModel, table=True): pass
class ReboundName(Record, table=True): pass
class ReboundModule(sm.SQLModel, table=True): pass
""",
            "wildcard.py": """from sqlmodel import SQLModel
class Shared(SQLModel): pass
from other import *
class Uncertain(SQLModel, table=True): pass
class UncertainBase(Shared, table=True): pass
""",
        })
        self.assertEqual([node for node in graph["nodes"] if node["type"] == "model"], [])


if __name__ == "__main__":
    unittest.main()
