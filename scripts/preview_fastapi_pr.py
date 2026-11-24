"""Compare two local Git commits without importing the target application."""
import argparse
import ast
from collections import Counter, defaultdict
from pathlib import PurePosixPath
import subprocess
import sys

try:
    from .fastapi_routes import CONSTRUCTORS, HTTP, collect_fastapi_routes
    from .preview_migration_evidence import migration_operations
    from .python_module_scope import FUNCTIONS, module_scope
    from .sqlmodel_models import collect_sqlmodel_classes
except ImportError:
    from fastapi_routes import CONSTRUCTORS, HTTP, collect_fastapi_routes
    from preview_migration_evidence import migration_operations
    from python_module_scope import FUNCTIONS, module_scope
    from sqlmodel_models import collect_sqlmodel_classes


MAX_PYTHON_FILES = 100
MAX_SOURCE_BYTES = 64 * 1024
REGULAR_FILE = {"100644", "100755"}
ROUTE_LIMITS = {
    "fastapi_conditional_registration": "조건부 라우트 등록 확인",
    "fastapi_handler_not_resolved": "핸들러 이름의 연결 확인",
    "fastapi_router_prefix_not_resolved": "라우터 접두어 확인",
    "fastapi_route_path_not_resolved": "동적으로 결정되는 경로 확인",
    "fastapi_include_prefix_not_resolved": "라우터를 등록할 때 적용되는 접두어 확인",
    "fastapi_include_not_resolved": "라우터를 연결한 뒤의 전체 경로 확인",
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, check=True
    ).stdout


def changed_files(repo, base, head, paths):
    raw = git(repo, "--literal-pathspecs", "diff", "--raw", "-z", "--no-abbrev",
              "--no-renames", "--no-ext-diff", "--no-textconv", "--no-relative", "--no-color",
              base, head, "--", *paths).split(b"\0")
    for header, path in zip(raw[::2], raw[1::2]):
        old_mode, new_mode, old_blob, new_blob, _ = header[1:].decode("ascii").split()
        yield path.decode("utf-8", errors="surrogateescape"), (
            (old_mode, old_blob), (new_mode, new_blob)
        )


def function_arguments(arguments):
    return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
            *([arguments.vararg] if arguments.vararg else []),
            *([arguments.kwarg] if arguments.kwarg else [])]


def factory_routes(tree, path, scope):
    """Reuse static route rules inside directly declared factory functions.

    Inherit only unique FastAPI imports. Parameters and local assignments take
    precedence, regardless of their execution order inside the function.
    These are declarations in a function, not proof that it is called.
    """
    _, global_bindings, global_stars = scope
    found, unresolved = defaultdict(list), []
    imports = []
    for factory in tree.body:
        if isinstance(factory, (ast.Import, ast.ImportFrom)):
            imports.append(factory)
        if (not isinstance(factory, FUNCTIONS) or factory.decorator_list
                or global_bindings[factory.name] != 1):
            continue
        local_tree = ast.Module(body=factory.body, type_ignores=[])
        nodes, local_bindings, _ = module_scope(local_tree)
        for argument in function_arguments(factory.args):
            local_bindings[argument.arg] += 1
        if any(isinstance(node, (ast.Global, ast.Nonlocal)) for node in nodes):
            continue
        inherited = []
        for imported in imports if not global_stars else []:
            if isinstance(imported, ast.ImportFrom):
                if imported.level or imported.module != "fastapi":
                    continue
                aliases = [alias for alias in imported.names if alias.name in CONSTRUCTORS]
            else:
                aliases = [alias for alias in imported.names if alias.name == "fastapi"]
            aliases = [alias for alias in aliases
                       if global_bindings[alias.asname or alias.name] == 1
                       and not local_bindings[alias.asname or alias.name]]
            if not aliases:
                continue
            copied = (ast.ImportFrom(module="fastapi", names=aliases, level=0)
                      if isinstance(imported, ast.ImportFrom) else ast.Import(names=aliases))
            inherited.append(ast.copy_location(copied, imported))
        local_tree.body = inherited + factory.body
        local_scope = module_scope(local_tree)
        for argument in function_arguments(factory.args):
            local_scope[1][argument.arg] += 1
        routes, unknown = collect_fastapi_routes(local_tree, path, local_scope)
        handlers = {node.name: node for node in factory.body if isinstance(node, FUNCTIONS)}
        for route in routes:
            key = (route["method"], route["path"], factory.name)
            found[key].append((route["line"], handlers[route["handler"]]))
        unresolved.extend(dict(item, factory=factory.name) for item in unknown)
    return found, unresolved


def declarations(tree, path, selected_models):
    scope = module_scope(tree)
    routes, unresolved = collect_fastapi_routes(tree, path, scope)
    handlers = {node.name: node for node in tree.body if isinstance(node, FUNCTIONS)}
    by_route = defaultdict(list)
    for route in routes:
        name = (route["method"], route["path"], "")
        # Multiple identical registrations are possible. Preserve their multiplicity.
        by_route[name].append((route["line"], handlers[route["handler"]]))
    nested, unknown = factory_routes(tree, path, scope)
    by_route.update(nested)
    unresolved.extend(unknown)
    recognized = collect_sqlmodel_classes(tree, scope)
    models = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if recognized.get(node) or node.name in selected_models:
            models[node.name] = node
    return by_route, models, unresolved


def decorator_response(handler, line):
    for decorator in handler.decorator_list:
        if isinstance(decorator, ast.Call) and decorator.lineno == line:
            for keyword in decorator.keywords:
                if keyword.arg == "response_model":
                    return short_expression(keyword.value)
    return None


def short_expression(node):
    expression = ast.unparse(node)
    return expression if len(expression) <= 100 else expression[:99] + "…"


def sort_calls(handler):
    calls = defaultdict(list)
    nodes = list(reversed(handler.body))
    while nodes:
        node = nodes.pop()
        if isinstance(node, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
            continue
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "order_by" and node.args):
            key = tuple(ast.dump(arg) for arg in node.args)
            terms = ", ".join(short_expression(arg) for arg in node.args)
            calls[key].append((node.lineno, terms))
        nodes.extend(reversed(list(ast.iter_child_nodes(node))))
    return calls


def changed_sort_calls(before, after):
    for key in dict.fromkeys((*after, *before)):
        old, new = before.get(key, []), after.get(key, [])
        if len(old) != len(new):
            occurrences = new or old
            lines = ", ".join(str(line) for line in sorted({line for line, _ in occurrences}))
            snapshot = "이후" if new else "이전"
            yield f"{occurrences[0][1]} · {len(old)} → {len(new)}건 ({snapshot} {lines}행)"


def route_changes(path, before, after):
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key, []), after.get(key, [])
        if [ast.dump(node) for _, node in old] == [ast.dump(node) for _, node in new]:
            continue
        method, url, factory = key
        name = f"{method} {url}" + (f" (함수 {factory})" if factory else "")
        line, _ = (new or old)[0]
        location = f"{path}:{line}" + ("" if new else " (이전 커밋)")
        if not old or not new:
            action = "추가" if new else "삭제"
            changes.append(f"{action} · {name} · {location}")
            if len(new or old) == 1:
                response = decorator_response((new or old)[0][1], line)
                if response:
                    changes.append(f"  응답 모델 선언 · {response}")
        elif len(old) != 1 or len(new) != 1:
            changes.append(f"선언 수정 · {name} · {location} · 동일 경로의 등록 {len(old)} → {len(new)}건")
        else:
            old_line, old_handler = old[0]
            new_line, new_handler = new[0]
            changes.append(f"핸들러 또는 선언 수정 · {name} · {location}")
            old_response = decorator_response(old_handler, old_line)
            new_response = decorator_response(new_handler, new_line)
            if old_response != new_response:
                changes.append(f"  응답 모델 선언 · {old_response or '명시 없음'} → {new_response or '명시 없음'}")
            elif new_response:
                changes.append(f"  응답 모델 선언 · {new_response}")
            if ast.dump(old_handler.args) != ast.dump(new_handler.args):
                changes.append("  핸들러 인자 선언 변경")
                old_args = {arg.arg: arg for arg in function_arguments(old_handler.args)}
                new_args = {arg.arg: arg for arg in function_arguments(new_handler.args)}
                for argument in sorted(old_args.keys() ^ new_args.keys()):
                    arg = new_args.get(argument) or old_args[argument]
                    action = "추가" if argument in new_args else "삭제"
                    annotation = f": {short_expression(arg.annotation)}" if arg.annotation else ""
                    changes.append(f"  인자 {action} · {argument}{annotation}")
            old_sort, new_sort = sort_calls(old_handler), sort_calls(new_handler)
            for term in changed_sort_calls(old_sort, new_sort):
                changes.append(f"  order_by 호출 · {term}")
    return changes


def annotated_fields(model):
    return {
        item.target.id: item for item in model.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    }


def model_changes(path, before, after):
    changes = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)
        if old is None or new is None:
            action = "추가" if new is not None else "삭제"
            location = f"{path}:{(new or old).lineno}" + ("" if new is not None else " (이전 커밋)")
            changes.append(f"클래스 {action} · {name} · {location}")
        old_fields = annotated_fields(old) if old is not None else {}
        new_fields = annotated_fields(new) if new is not None else {}
        for field in sorted(old_fields.keys() | new_fields.keys()):
            previous, current = old_fields.get(field), new_fields.get(field)
            if previous is None:
                action, detail = "추가", short_expression(current.annotation)
            elif current is None:
                action, detail = "삭제", short_expression(previous.annotation)
            elif ast.dump(previous) != ast.dump(current):
                action = "수정"
                old_type, new_type = short_expression(previous.annotation), short_expression(current.annotation)
                detail = f"{old_type} → {new_type}" if old_type != new_type else f"{new_type} · 선언값 변경"
            else:
                continue
            location = f"{path}:{(current or previous).lineno}" + ("" if current is not None else " (이전 커밋)")
            changes.append(f"필드 {action} · {name}.{field} · {detail} · {location}")
            old_value = short_expression(previous.value) if previous is not None and previous.value is not None else "지정 없음"
            new_value = short_expression(current.value) if current is not None and current.value is not None else "지정 없음"
            if old_value != new_value:
                changes.append(f"  필드 선언값 · {name}.{field} · {old_value} → {new_value}")
    return changes


def read_tree(repo, path, mode, blob):
    if mode == "000000":
        return ast.Module(body=[], type_ignores=[]), None
    if mode not in REGULAR_FILE:
        return None, "일반 파일이 아님"
    if int(git(repo, "cat-file", "-s", blob)) > MAX_SOURCE_BYTES:
        return None, "64 KiB 초과"
    try:
        return ast.parse(git(repo, "cat-file", "blob", blob), filename=path), None
    except (SyntaxError, ValueError, RecursionError):
        return None, "Python 구문을 읽지 못함"


def migration_changes(path, before, after):
    changes = []
    old_operations, new_operations = migration_operations(before), migration_operations(after)
    for label, operations, other in (("추가", new_operations, old_operations), ("삭제", old_operations, new_operations)):
        remaining = Counter(detail for _, detail in other)
        for line, detail in operations:
            if remaining[detail]:
                remaining[detail] -= 1
            else:
                previous = " (이전 커밋)" if label == "삭제" else ""
                changes.append(f"선언 {label} · {detail} · {path}:{line}{previous}")
    return changes


def scoped_route_candidates(tree):
    """Keep syntactic candidates separate from resolved FastAPI registrations."""
    candidates = defaultdict(list)

    def visit(node, parents):
        if isinstance(node, (*FUNCTIONS, ast.ClassDef)):
            name = (*parents, node.name)
            if isinstance(node, FUNCTIONS):
                decorators = [item for item in node.decorator_list
                              if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
                              and item.func.attr in HTTP]
                if decorators:
                    candidates[".".join(name)].extend((item.lineno, node) for item in decorators)
            parents = name
        for child in ast.iter_child_nodes(node):
            visit(child, parents)

    visit(tree, ())
    return candidates


def scoped_route_gaps(before, after, old_routes, new_routes):
    """Keep unresolved declarations out of both sides of a comparison.

    Losing a static binding is not evidence that a route was deleted. Likewise,
    gaining one must not invent a new route when the old declaration was unknown.
    """
    old, new = scoped_route_candidates(before), scoped_route_candidates(after)
    resolved = [{item for entries in routes.values() for item in entries}
                for routes in (old_routes, new_routes)]
    for name in sorted(old.keys() | new.keys()):
        previous, current = old.get(name, []), new.get(name, [])
        if all(item in known for entries, known in zip((previous, current), resolved)
               for item in entries):
            continue
        # A factory's context may change even when its handler AST is identical.
        transition = any(item in known for entries, known in zip((previous, current), resolved)
                         for item in entries)
        for entries, routes in ((previous, old_routes), (current, new_routes)):
            blocked = {node for _, node in entries}
            for key in list(routes):
                routes[key] = [item for item in routes[key] if item[1] not in blocked]
                if not routes[key]:
                    del routes[key]
        if not transition and [ast.dump(node) for _, node in previous] == [ast.dump(node) for _, node in current]:
            continue
        lines = ", ".join(str(line) for line, _ in (current or previous))
        snapshot = "이후" if current else "이전"
        context = "함수·클래스 내부 " if "." in name else ""
        yield f"자동 라우트 비교 범위 밖 · {context}HTTP 데코레이터 후보 {name} ({snapshot} {lines}행)"


def compare_trees(files, selected_models, selected_responses):
    """Compare parsed snapshots shared by the local CLI and browser preview."""
    routes, models, responses, migrations, review = [], [], [], [], []
    for path, trees, source_reasons in files:
        reasons = list(source_reasons)
        evidence_count = len(routes) + len(models) + len(responses) + len(migrations)
        migration = any(part in {"migrations", "alembic"} for part in PurePosixPath(path).parts[:-1])
        if migration:
            reasons.append("마이그레이션 내용과 기존 데이터 영향 확인")
        if len(trees) == 2 and migration:
            migrations.extend(migration_changes(path, *trees))
        elif len(trees) == 2:
            response_names = selected_responses.get(path, set())
            model_names = selected_models.get(path, set())
            requested = model_names | response_names
            before, after = (declarations(tree, path, requested) for tree in trees)
            old_routes, old_models, old_unknown = before
            new_routes, new_models, new_unknown = after
            reasons.extend(scoped_route_gaps(*trees, old_routes, new_routes))
            routes.extend(route_changes(path, old_routes, new_routes))
            old_responses = {name: old_models[name] for name in response_names & old_models.keys()}
            new_responses = {name: new_models[name] for name in response_names & new_models.keys()}
            responses.extend(model_changes(path, old_responses, new_responses))
            for name in response_names - model_names:
                old_models.pop(name, None)
                new_models.pop(name, None)
            models.extend(model_changes(path, old_models, new_models))
            for label, unknown in (("이전", old_unknown), ("이후", new_unknown)):
                reasons.extend(f"{label} {item['line']}행 · "
                               + (f"함수 {item['factory']} · " if 'factory' in item else "")
                               + ROUTE_LIMITS.get(item['reason'], item['reason'])
                               for item in unknown)
            found = old_models.keys() | new_models.keys() | old_responses.keys() | new_responses.keys()
            for name in sorted(requested - found):
                reasons.append(f"사용자가 지정한 클래스가 없음 ({name})")
        # Even with zero parser errors a custom router, ORM, or settings file may matter.
        if not reasons and evidence_count == len(routes) + len(models) + len(responses) + len(migrations):
            reasons.append("자동으로 분류한 변경 단서 없음")
        review.append((path, reasons))
    return routes, models, responses, migrations, review


def preview(repo, base_ref, head_ref, paths, selected_models, selected_responses):
    base, head = (git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
                  .decode("ascii").strip() for ref in (base_ref, head_ref))

    def snapshots():
        analyzed = 0
        for path, blobs in changed_files(repo, base, head, paths):
            trees, reasons = [], []
            if path.endswith(".py"):
                if analyzed >= MAX_PYTHON_FILES:
                    reasons.append("파일 수 한도로 분석하지 못함")
                else:
                    analyzed += 1
                    for label, (mode, blob) in zip(("이전", "이후"), blobs):
                        tree, error = read_tree(repo, path, mode, blob)
                        if error:
                            reasons.append(f"{label}: {error}")
                        else:
                            trees.append(tree)
            yield path, trees, reasons

    return base, head, *compare_trees(snapshots(), selected_models, selected_responses)


def terminal_text(value):
    return "".join(char if char.isprintable() else ascii(char)[1:-1] for char in value)


def model_selectors(parser, option, selectors):
    selected = defaultdict(set)
    for selector in selectors:
        path, separator, name = selector.rpartition(":")
        if not separator or not path.endswith(".py") or not name.isidentifier():
            parser.error(f"{option} 값은 저장소 상대 경로 FILE.py:Class 형식이어야 합니다.")
        selected[path].add(name)
    return selected


def print_section(title, entries):
    print(f"\n{title}")
    for entry in entries or ["지원 범위에서 감지된 변경 없음"]:
        print(terminal_text(entry) if entry.startswith("  ") else "- " + terminal_text(entry))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.version_info < (3, 10):
        parser.exit(2, "Python 3.10 이상이 필요합니다. 대상 코드가 요구하는 Python 버전을 사용하세요.\n")
    parser.add_argument("--repo", default=".", help="대상 Git 저장소 경로")
    parser.add_argument("--base", required=True, help="비교 기준 커밋 또는 ref")
    parser.add_argument("--head", required=True, help="비교 대상 커밋 또는 ref")
    parser.add_argument("--focus", choices=("all", "api", "db"), default="all",
                        help="리뷰 목적 (api: API 소비자, db: DB 운영, all: 모두)")
    parser.add_argument("--path", action="append", default=[], help="비교할 저장소 상대 경로 (반복 가능)")
    parser.add_argument("--model", action="append", default=[], metavar="FILE:CLASS",
                        help="필드를 비교할 모델 클래스 수동 지정 (반복 가능)")
    parser.add_argument("--response-model", action="append", default=[], metavar="FILE:CLASS",
                        help="API 결과에 필드 변경을 표시할 응답 클래스 (반복 가능)")
    args = parser.parse_args()
    selected_models = model_selectors(parser, "--model", args.model)
    selected_responses = model_selectors(parser, "--response-model", args.response_model)
    try:
        base, head, routes, models, responses, migrations, review = preview(
            args.repo, args.base, args.head, args.path, selected_models, selected_responses
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        details = exc.stderr.decode(errors="replace").strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        parser.exit(2, f"Git 비교를 실행할 수 없습니다: {terminal_text(details)}\n")
    focus_labels = {"all": "전체", "api": "API 리뷰", "db": "DB 리뷰"}
    print(f"FastAPI PR 미리보기 · {focus_labels[args.focus]} · {base[:12]} → {head[:12]}")
    if args.path:
        print("비교 경로:", terminal_text(", ".join(args.path)))
    if args.model and args.focus != "api":
        print("사용자 지정 모델:", terminal_text(", ".join(args.model)))
    if args.response_model and args.focus != "db":
        print("사용자 지정 응답 모델:", terminal_text(", ".join(args.response_model)))
    if args.focus in {"all", "api"}:
        print_section("라우트와 핸들러 (선언 범위)", routes)
        if args.response_model:
            print_section("지정한 응답 모델의 필드", responses)
    if args.focus in {"all", "db"}:
        print_section("마이그레이션 선언", migrations)
        print_section("테이블 모델과 지정한 DB 모델의 필드", models)
    if args.focus == "api" and not args.response_model and review:
        print("\n응답 클래스 내부의 변경도 비교하려면 --response-model FILE.py:Class를 지정하세요.")
    print("\n변경 파일 및 수동 확인")
    for path, reasons in review:
        note = f" ({'; '.join(reasons)})" if reasons else ""
        print("-", terminal_text(path + note))
    if not review:
        print("- 지정 범위에 변경 파일 없음")
    print("\n정적 비교입니다. 전체 등록 경로, 자동 탐지하지 못한 ORM, 실제 DB 스키마는 별도 확인이 필요합니다.")


if __name__ == "__main__":
    # Git allows non-UTF-8 filenames; display undecodable bytes without aborting the report.
    sys.stdout.reconfigure(errors="backslashreplace")
    main()
