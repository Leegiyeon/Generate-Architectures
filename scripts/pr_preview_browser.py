"""Browser entry point for public source snapshots. Target code is only parsed."""
import ast
from collections import defaultdict
import json

from .preview_fastapi_pr import MAX_PYTHON_FILES, MAX_SOURCE_BYTES, compare_trees
from .python_module_scope import module_scope
from .sqlmodel_models import collect_sqlmodel_classes
from .pr_preview_structure import structure_snapshots


def selectors(values):
    selected = defaultdict(set)
    for value in values:
        path, separator, name = value.rpartition(":")
        if not separator or not path.endswith(".py") or not name.isidentifier():
            raise ValueError("모델은 파일.py:클래스 형식으로 입력해 주세요.")
        selected[path].add(name)
    return selected


def analyze(payload):
    selected_models = selectors(payload.get("models", []))
    selected_responses = selectors(payload.get("responses", []))
    paths = [path.rstrip("/") for path in payload.get("paths", [])]
    files, parsed_count, python_count = [], 0, 0
    for source in payload["files"]:
        path = source["path"]
        if paths and not any(path == prefix or path.startswith(prefix + "/") for prefix in paths):
            continue
        trees = []
        reasons = list(source.get("warnings", []))
        if path.endswith(".py"):
            python_count += 1
            if python_count > MAX_PYTHON_FILES:
                reasons.append("파일 수 한도로 분석하지 못함")
            else:
                for key, label in (("before", "이전"), ("after", "이후")):
                    if source.get(key) is None:
                        reasons.append(f"{label} 소스를 읽지 못함")
                        continue
                    text = source[key]
                    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
                        reasons.append(f"{label} 파일이 64 KiB를 초과함")
                        continue
                    try:
                        tree = ast.parse(text, filename=path)
                    except (SyntaxError, ValueError, RecursionError):
                        reasons.append(f"{label} Python 구문을 읽지 못함")
                        continue
                    trees.append(tree)
                    # SQLModel DTOs are declaration evidence. Custom classes stay opt-in.
                    for node, is_table in collect_sqlmodel_classes(tree, module_scope(tree)).items():
                        if not is_table:
                            selected_responses[path].add(node.name)
                if len(trees) == 2:
                    parsed_count += 1
        files.append((path, trees, reasons))
    routes, models, responses, migrations, review = compare_trees(
        files, selected_models, selected_responses
    )
    return {
        "routes": routes, "models": models, "responses": responses,
        "migrations": migrations, "review": review,
        "parsed_files": parsed_count, "python_files": python_count,
        "changed_files": len(files),
        "structure": structure_snapshots(files, selected_models, selected_responses),
    }


def analyze_json(payload_json):
    return json.dumps(analyze(json.loads(payload_json)), ensure_ascii=False)
