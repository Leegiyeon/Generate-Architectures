"""Build source-linked declaration snapshots from the PR files already parsed."""
import ast
import json

from .preview_fastapi_pr import annotated_fields, declarations, scoped_route_gaps, short_expression


MAX_STRUCTURE_NODES = 80


def _identifier(path, kind, key):
    # Paths and declaration names can contain separators; encode the whole key.
    return json.dumps([path, kind, key], ensure_ascii=False, separators=(",", ":"))


def _field_detail(model):
    fields = list(annotated_fields(model).items())
    labels = [f"{name}: {short_expression(field.annotation)}" for name, field in fields[:8]]
    if len(fields) > 8:
        labels.append(f"외 {len(fields) - 8}개")
    return "직접 선언 필드 · " + (", ".join(labels) if labels else "없음")


def _snapshot(files, side, selected_responses, declarations_by_path):
    nodes, edges, fingerprints = [], [], {}

    def append(path, kind, key, label, detail, source, line=None):
        identifier = _identifier(path, kind, key)
        nodes.append({"id": identifier, "kind": kind, "label": label,
                      "path": path, "line": line or source.lineno, "detail": detail})
        fingerprints[identifier] = ast.dump(source, include_attributes=False)
        return identifier

    for path, trees, _ in files:
        if not path.endswith(".py") or len(trees) != 2:
            continue
        tree = trees[side]
        if not tree.body:
            # Added/deleted files use an empty AST for the absent side. Its
            # existence cannot be established from this snapshot alone.
            continue
        parent = append(path, "file", "", path, "Python 파일", tree, line=1)
        routes, models, _ = declarations_by_path[path][side]

        def declaration(kind, key, label, detail, source, line=None):
            identifier = append(path, kind, key, label, detail, source, line)
            edges.append({"source": parent, "target": identifier, "kind": "defines",
                          "evidence": {"path": path, "line": line or source.lineno}})

        for (method, route, factory), registrations in sorted(routes.items()):
            for index, (line, handler) in enumerate(registrations):
                detail = "핸들러 " + handler.name
                if factory:
                    detail += f" · 함수 {factory} 내부 · 호출 여부 미확인"
                declaration("route", [method, route, factory, index], f"{method} {route}",
                            detail, handler, line=line)
        for name, model in sorted(models.items()):
            declaration("model", name, name, _field_detail(model), model)
        responses = {model.name: model for model in tree.body
                     if isinstance(model, ast.ClassDef)
                     and model.name in selected_responses.get(path, set())
                     and model.name not in models}
        for name, model in sorted(responses.items()):
            declaration("response", name, name, _field_detail(model), model)
    return nodes, edges, fingerprints


def structure_snapshots(files, selected_models, selected_responses):
    """Compare full declaration sets, then cap each displayed graph independently.

    Edges mean that a file declares a route/model, never execution or DB access.
    A parse failure on either side excludes both sides instead of inventing a
    deletion/addition. Status comparisons ignore source line movements.
    """
    declarations_by_path, uncertain_routes = {}, []
    for path, trees, _ in files:
        if path.endswith(".py") and len(trees) == 2:
            pair = [declarations(tree, path, selected_models.get(path, set())) for tree in trees]
            if list(scoped_route_gaps(*trees, pair[0][0], pair[1][0])):
                uncertain_routes.append(path)
            declarations_by_path[path] = pair
    before = _snapshot(files, 0, selected_responses, declarations_by_path)
    after = _snapshot(files, 1, selected_responses, declarations_by_path)

    def graph(current, other, absent_status):
        nodes, edges, fingerprints = current
        for item in nodes:
            identifier = item["id"]
            item["status"] = (absent_status if identifier not in other[2] else
                              "unchanged" if fingerprints[identifier] == other[2][identifier]
                              else "modified")
        visible = nodes[:MAX_STRUCTURE_NODES]
        identifiers = {item["id"] for item in visible}
        return {"nodes": visible,
                "edges": [item for item in edges if item["source"] in identifiers
                          and item["target"] in identifiers],
                "omitted_nodes": len(nodes) - len(visible)}

    return {"before": graph(before, after, "removed"),
            "after": graph(after, before, "added"),
            "uncertain_route_paths": uncertain_routes,
            "unreadable_paths": [path for path, trees, _ in files
                                 if path.endswith(".py") and len(trees) != 2]}
