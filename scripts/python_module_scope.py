"""Inspect bindings in a Python module without entering nested scopes."""
import ast
from collections import Counter


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _module_nodes(tree):
    pending = list(reversed(tree.body))
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, ast.comprehension):
            # The iteration target is local; a walrus in the expressions can bind outside.
            pending.extend(reversed([node.iter, *node.ifs]))
        elif not isinstance(node, (*FUNCTIONS, ast.ClassDef, ast.Lambda)):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def position(node):
    return node.lineno, node.col_offset


def module_scope(tree):
    nodes = list(_module_nodes(tree))
    names = Counter()
    star_imports = []
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.names[0].name == "*":
                star_imports.append(position(node))
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
    return nodes, names, star_imports


def may_be_shadowed(star_imports, declaration, use):
    start, end = position(declaration), position(use)
    return any(start < wildcard < end for wildcard in star_imports)
