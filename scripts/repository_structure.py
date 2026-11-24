"""Inspect a bounded Python repository snapshot without importing target code.

Import edges identify an explicit module's unique path under the supplied source
root. They do not establish runtime loading, symbol re-exports, router mounting,
function calls, or infrastructure. ``from package import child`` links only to
the explicit ``package`` module, never a guessed child module.
The optional complete ``known_paths`` tree retains unread candidates for import
ambiguity checks; only actual, parsed source snapshots become graph nodes.
"""
import ast
from collections import defaultdict
import json

from .preview_fastapi_pr import (
    MAX_PYTHON_FILES, MAX_SOURCE_BYTES, ROUTE_LIMITS, annotated_fields, declarations,
)


MAX_NODES = 80
MAX_DECLARATIONS = 20
MAX_UNRESOLVED = 100
MAX_EDGES = 400
MAX_WARNINGS = 200
MAX_KNOWN_PATHS = 100000
MAX_PATH_LENGTH = 1000


def _path(value, root=False):
    if root and value in ("", "."):
        return ""
    if (not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH
            or "\\" in value or "\0" in value):
        raise ValueError("저장소 상대 경로가 필요합니다.")
    if root:
        value = value.rstrip("/")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or ":" in parts[0]:
        raise ValueError("절대 경로나 상위 경로는 사용할 수 없습니다.")
    return value


def _label(node):
    value = ast.unparse(node)
    return value if len(value) <= 200 else value[:199] + "…"


def _module(path, root):
    relative = path[len(root) + 1:] if root else path
    parts = relative.split("/")
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][:-3]
    return tuple(parts) if all(part.isidentifier() for part in parts) else None


def _declarations(tree, path):
    routes, models, unknown = declarations(tree, path, set())
    result = []
    for (method, route, factory), registrations in sorted(routes.items()):
        for line, handler in registrations:
            detail = "핸들러 " + handler.name
            if factory:
                detail += f" · 함수 {factory} 내부 · 호출 여부 미확인"
            result.append({"kind": "route", "label": f"{method} {route}",
                           "line": line, "detail": detail})
    route_count = len(result)
    for name, model in sorted(models.items()):
        fields = list(annotated_fields(model))
        detail = "직접 선언 필드 · " + (", ".join(fields[:8]) if fields else "없음")
        if len(fields) > 8:
            detail += f" 외 {len(fields) - 8}개"
        result.append({"kind": "model", "label": name, "line": model.lineno, "detail": detail})
    warnings = [f"{path}:{item['line']} · {ROUTE_LIMITS.get(item['reason'], '라우트 선언 추가 확인')}"
                for item in unknown]
    return {"id": path, "kind": "file", "label": path, "path": path, "line": 1,
            "detail": f"라우트 선언 {route_count}개 · 테이블 선언 {len(models)}개",
            "declarations": result[:MAX_DECLARATIONS],
            "omitted_declarations": max(0, len(result) - MAX_DECLARATIONS)}, warnings


def analyze(payload):
    if not isinstance(payload, dict):
        raise ValueError("저장소 스냅샷 자료가 필요합니다.")
    root = _path(payload.get("root", "."), root=True)
    sources = payload.get("files")
    if not isinstance(sources, list):
        raise ValueError("분석할 파일 목록이 필요합니다.")
    selected, seen = [], set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("파일 자료 형식을 확인해 주세요.")
        path = _path(source.get("path"))
        if path in seen:
            raise ValueError("중복 파일 경로는 분석할 수 없습니다: " + path)
        seen.add(path)
        if path.endswith(".py") and (not root or path.startswith(root + "/")):
            selected.append(source)
    selected.sort(key=lambda source: source["path"])
    known_paths = set()
    if "known_paths" in payload:
        known = payload["known_paths"]
        if not isinstance(known, list) or len(known) > MAX_KNOWN_PATHS:
            raise ValueError("전체 파일 경로 목록은 최대 100000개의 경로여야 합니다.")
        for value in known:
            path = _path(value)
            if path.endswith(".py") and (not root or path.startswith(root + "/")):
                known_paths.add(path)
    # Even an incomplete supplied tree must not hide a source-side collision.
    known_paths.update(source["path"] for source in selected)
    modules = defaultdict(list)
    for path in sorted(known_paths):
        module = _module(path, root)
        if module is not None:
            modules[module].append(path)

    trees, nodes, unreadable, warnings = {}, [], [], []
    for index, source in enumerate(selected):
        path = source["path"]
        notes = source.get("warnings", [])
        if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
            raise ValueError("파일 경고 자료 형식을 확인해 주세요.")
        warnings.extend(f"{path} · {note}" for note in notes)
        text = source.get("after")
        reason = None
        if index >= MAX_PYTHON_FILES:
            reason = "Python 파일 100개 한도로 분석하지 못함"
        elif not isinstance(text, str):
            reason = "소스를 읽지 못함"
        else:
            try:
                if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
                    reason = "파일이 64 KiB를 초과함"
                else:
                    trees[path] = ast.parse(text, filename=path)
            except (SyntaxError, ValueError, RecursionError, UnicodeEncodeError):
                reason = "Python 구문을 읽지 못함"
        if reason:
            unreadable.append(path)
            warnings.append(f"{path} · {reason}")
        else:
            node, notes = _declarations(trees[path], path)
            nodes.append(node)
            warnings.extend(notes)

    edges, unresolved = [], []

    def unknown(path, node, label, reason):
        unresolved.append({"path": path, "line": node.lineno, "label": label, "reason": reason})

    def connect(path, node, module, label):
        for length in range(1, len(module)):
            prefix = module[:length]
            parents = modules.get(prefix, [])
            reason = None
            if len(parents) > 1:
                reason = "상위 모듈에 여러 파일 후보가 있어 하위 경로를 연결하지 않음"
            elif parents and parents[0].split("/")[-1] != "__init__.py":
                reason = "상위 경로가 일반 모듈 파일이므로 하위 패키지 경로를 연결하지 않음"
            elif parents and parents[0] not in trees:
                reason = "상위 패키지 소스를 읽지 못해 하위 경로를 연결하지 않음"
            if reason:
                unknown(path, node, label, ".".join(prefix) + " · " + reason)
                return
            # No explicit initializer can still be a namespace package. This
            # permits a static path candidate, not proof of runtime loading.
        candidates = modules.get(module, [])
        if len(candidates) != 1:
            reason = ("같은 모듈에 여러 파일 후보가 있어 연결하지 않음" if candidates else
                      "외부 패키지·선택 범위 밖·해석 불가 중 어느 경우인지 확인 필요")
            unknown(path, node, label, reason)
        elif candidates[0] not in trees:
            unknown(path, node, label, "대상 파일 소스를 읽지 못해 연결하지 않음")
        elif candidates[0] == path:
            warnings.append(f"{path}:{node.lineno} · 같은 파일을 가리키는 import는 도표에서 생략함")
        else:
            edges.append({"source": path, "target": candidates[0], "kind": "imports", "label": label,
                          "evidence": {"path": path, "line": node.lineno}})

    for path, tree in trees.items():
        relative = path[len(root) + 1:] if root else path
        package = tuple(relative.split("/")[:-1])
        direct = {id(node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))}
        dynamic_names, dynamic_modules = {"__import__"}, set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dynamic_modules.update(alias.asname or alias.name for alias in node.names if alias.name == "importlib")
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module == "importlib":
                dynamic_names.update(alias.asname or alias.name for alias in node.names if alias.name == "import_module")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and id(node) not in direct:
                unknown(path, node, _label(node), "조건부·함수·클래스 내부 import는 직접 모듈 연결에 포함하지 않음")
            elif isinstance(node, ast.Call):
                function = node.func
                if ((isinstance(function, ast.Name) and function.id in dynamic_names)
                        or (isinstance(function, ast.Attribute) and function.attr == "import_module"
                            and isinstance(function.value, ast.Name) and function.value.id in dynamic_modules)):
                    unknown(path, node, _label(function) + "(…)", "동적 import 형태의 호출은 실제 대상을 확인하지 않음")
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    label = "import " + alias.name + (" as " + alias.asname if alias.asname else "")
                    connect(path, node, tuple(alias.name.split(".")), label)
            elif isinstance(node, ast.ImportFrom):
                label = _label(node)
                if node.level:
                    if node.level > len(package):
                        unknown(path, node, label, "상대 import가 지정한 Python 소스 루트를 벗어남")
                        continue
                    module = package[:len(package) - node.level + 1]
                else:
                    module = ()
                module += tuple(node.module.split(".")) if node.module else ()
                connect(path, node, module, label)

    visible = nodes[:MAX_NODES]
    identifiers = {node["id"] for node in visible}
    shown_edges = [edge for edge in edges if edge["source"] in identifiers
                   and edge["target"] in identifiers][:MAX_EDGES]
    unresolved.sort(key=lambda item: (item["path"], item["line"], item["label"], item["reason"]))
    warnings = sorted(set(warnings))
    if len(warnings) > MAX_WARNINGS:
        warnings = warnings[:MAX_WARNINGS - 1] + [f"추가 경고 {len(warnings) - MAX_WARNINGS + 1}개는 표시 한도로 생략함"]
    return {"nodes": visible, "edges": shown_edges, "unresolved": unresolved[:MAX_UNRESOLVED],
            "unreadable_paths": unreadable, "warnings": warnings,
            "python_files": len(selected), "parsed_files": len(trees),
            "omitted_nodes": len(nodes) - len(visible), "omitted_edges": len(edges) - len(shown_edges),
            "omitted_unresolved": max(0, len(unresolved) - MAX_UNRESOLVED)}


def analyze_json(payload_json):
    return json.dumps(analyze(json.loads(payload_json)), ensure_ascii=False)
