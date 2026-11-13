"""Identify explicit SQLModel table declarations in the same Python module."""
import ast

try:
    from .python_module_scope import may_be_shadowed
except ImportError:
    from python_module_scope import may_be_shadowed


def collect_sqlmodel_classes(tree, scope):
    """Map recognized classes to whether they explicitly declare a table."""
    _, bindings, star_imports = scope
    bases, modules, classes = {}, {}, {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "sqlmodel":
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == "SQLModel" and bindings[name] == 1:
                    bases[name] = node
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == "sqlmodel" and bindings[name] == 1:
                    modules[name] = node
        elif isinstance(node, ast.ClassDef) and len(node.bases) == 1:
            base = node.bases[0]
            if isinstance(base, ast.Name):
                declaration = bases.get(base.id)
            elif isinstance(base, ast.Attribute) and base.attr == "SQLModel" and isinstance(base.value, ast.Name):
                declaration = modules.get(base.value.id)
            else:
                continue
            if declaration is None or may_be_shadowed(star_imports, declaration, node):
                continue
            # A known SQLModel base takes precedence over the generic Base/Model heuristic.
            classes[node] = False
            if bindings[node.name] != 1 or node.decorator_list:
                continue
            if not node.keywords:
                bases[node.name] = node
            elif len(node.keywords) == 1:
                keyword = node.keywords[0]
                if keyword.arg == "table" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value is True:
                        classes[node] = True
                    elif keyword.value.value is False:
                        bases[node.name] = node
    return classes
