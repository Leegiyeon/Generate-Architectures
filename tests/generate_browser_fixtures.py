"""Supplement the ten golden reports with offline migration/cost browser cases."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.recommend_architecture import run
from test_golden_workloads import CASES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    output = Path(parser.parse_args().output).resolve()
    inventory = {
        "schema_version": "1.0",
        "servers": [{"id": "application-server-" + str(i), "role": "mixed",
                     "os": "linux", "db_engine": "postgresql", "access": "internal"}
                    for i in range(8)],
        "connections": [{"from": "application-server-0", "to": "application-server-1",
                         "purpose": "database"}],
    }
    for name, declared, cost in (("11-migration-no-inventory", False, False),
                                 ("12-migration-eight-servers", True, False),
                                 ("13-migration-cost-details", True, True)):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative, content in CASES[3]["files"].items():
                file = root / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content, encoding="utf-8")
            if declared:
                (root / ".architecture").mkdir()
                (root / ".architecture/onprem-inventory.json").write_text(
                    json.dumps(inventory), encoding="utf-8")
            if cost:
                sample = Path(__file__).resolve().parent.parent / "examples/cost-scenarios.example.json"
                (root / "cost.json").write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                run(root, output / name, analysis_goal="migrate_onprem",
                    cost_input="cost.json" if cost else None)
    print("3 synthetic migration/cost browser reports generated")


if __name__ == "__main__":
    main()
