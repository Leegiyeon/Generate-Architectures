"""Collect FastAPI decorator paths in their declaring app or router scope."""
import ast
from collections import Counter


HTTP = {"get", "post", "put", "patch", "delete", "options", "head"}
CONSTRUCTORS = {"FastAPI": "app_local", "APIRouter": "router_local"}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
MAX_ROUTE_PATH = 160


def _module_nodes(tree):
    """Include module control flow without walking into other binding scopes."""
    pending = list(reversed(tree.body))
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, ast.comprehension):
            # The iteration target is local; a walrus in the expressions can bind outside.
            pending.extend(reversed([node.iter, *node.ifs]))
        elif not isinstance(node, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _bindings(nodes):
    names = Counter()
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (*FUNCTIONS, ast.ClassDef, ast.ExceptHandler,
                               ast.MatchAs, ast.MatchStar)) and node.name:
            names[node.name] += 1
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names[node.rest] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names[node.id] += 1
        elif (isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del))
              and isinstance(node.value, ast.Name)):
            names[node.value.id] += 1
    return names


def _position(node):
    return node.lineno, node.col_offset


def _literal(call, keyword, *, positional=False, default=None):
    if any(arg.arg is None for arg in call.keywords):
        return None
    values = [arg.value for arg in call.keywords if arg.arg == keyword]
    if positional and call.args:
        if len(call.args) != 1:
            return None
        values.append(call.args[0])
    if not values:
        return default
    if len(values) != 1 or not isinstance(values[0], ast.Constant):
        return None
    value = values[0].value
    return value if isinstance(value, str) else None


def _prefix(call):
    if call.args:
        return None
    value = _literal(call, "prefix", default="")
    return value if value == "" or (value and value.startswith("/") and not value.endswith("/")) else None


def collect_fastapi_routes(tree, path):
    module_nodes = list(_module_nodes(tree))
    bindings = _bindings(module_nodes)
    imports, receivers = {}, {}
    star_imports = [_position(node) for node in module_nodes
                    if isinstance(node, ast.ImportFrom) and node.names[0].name == "*"]

    def may_be_shadowed(start, end):
        return any(_position(start) < position < _position(end) for position in star_imports)

    # In module order: use only unique, already declared import/assignment bindings.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "fastapi":
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name in CONSTRUCTORS and bindings[local] == 1:
                    imports[local] = (alias.name, node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "fastapi" and bindings[local] == 1:
                    imports[local] = ("fastapi", node)
        else:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            else:
                continue
            if not isinstance(target, ast.Name) or bindings[target.id] != 1 or not isinstance(value, ast.Call):
                continue
            func = value.func
            if isinstance(func, ast.Name) and func.id in imports:
                constructor, imported_at = imports[func.id]
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in imports:
                module, imported_at = imports[func.value.id]
                constructor = func.attr if module == "fastapi" else None
            else:
                continue
            if may_be_shadowed(imported_at, node):
                continue
            if constructor in CONSTRUCTORS:
                scope = CONSTRUCTORS[constructor]
                receivers[target.id] = (scope, _prefix(value) if scope == "router_local" else "", node)

    def receiver(call):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            return None
        base = call.func.value
        item = receivers.get(base.id) if isinstance(base, ast.Name) else None
        return item if (item and _position(item[2]) < _position(call)
                        and not may_be_shadowed(item[2], call)) else None

    routes, unresolved = [], []
    top_level = set(tree.body)

    def missing(node, reason):
        unresolved.append({"path": path, "line": node.lineno, "reason": "fastapi_" + reason})

    for node in module_nodes:
        if isinstance(node, FUNCTIONS):
            for decorator in node.decorator_list:
                item = receiver(decorator)
                if not item or decorator.func.attr not in HTTP:
                    continue
                scope, prefix, declaration = item
                url = _literal(decorator, "path", positional=True)
                if node not in top_level:
                    missing(decorator, "conditional_registration")
                elif bindings[node.name] != 1:
                    missing(decorator, "handler_not_resolved")
                elif prefix is None:
                    missing(decorator, "router_prefix_not_resolved")
                elif (url is None or (url and not url.startswith("/")) or not (prefix + url)
                      or len(prefix + url) > MAX_ROUTE_PATH
                      or any(ord(char) < 32 for char in prefix + url)):
                    missing(decorator, "route_path_not_resolved")
                else:
                    route = {"method": decorator.func.attr.upper(), "path": prefix + url,
                             "line": decorator.lineno, "handler": node.name, "route_scope": scope}
                    if prefix:
                        route["prefix_source"] = {"path": path, "line": declaration.lineno}
                    routes.append(route)
        elif isinstance(node, ast.Expr) and receiver(node.value) and node.value.func.attr == "include_router":
            # Includes copy a router's registrations at the call. Import, order and
            # conditional state are intentionally left unverified in this analyzer.
            if node not in top_level:
                missing(node.value, "conditional_registration")
            elif _literal(node.value, "prefix", default="") is None:
                missing(node.value, "include_prefix_not_resolved")
            else:
                missing(node.value, "include_not_resolved")
    return routes, unresolved
