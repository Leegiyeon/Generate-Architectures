"""Collect a limited set of Alembic upgrade declarations without executing them."""
import ast

try:
    from .python_module_scope import module_scope
except ImportError:
    from python_module_scope import module_scope


def _literal_name(value):
    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
        return value.value
    return None


def _arguments(call, names):
    if (len(call.args) > len(names) or any(isinstance(arg, ast.Starred) for arg in call.args)
            or any(keyword.arg is None for keyword in call.keywords)):
        return None
    arguments = dict(zip(names, call.args))
    for keyword in call.keywords:
        if keyword.arg in arguments:
            return None
        arguments[keyword.arg] = keyword.value
    return arguments


def _table_name(arguments):
    table = _literal_name(arguments.get("table_name"))
    schema_node = arguments.get("schema")
    if not table or schema_node is None:
        return table
    if isinstance(schema_node, ast.Constant) and schema_node.value is None:
        return table
    schema = _literal_name(schema_node)
    return f"{schema}.{table}" if schema else None


def migration_operations(tree: ast.Module) -> list[tuple[int, str]]:
    """Return source lines and descriptions for direct column declarations."""
    _, bindings, star_imports = module_scope(tree)
    upgrades = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade"]
    if star_imports or bindings["upgrade"] != 1 or len(upgrades) != 1:
        return []
    upgrade = upgrades[0]
    if upgrade.decorator_list:
        return []

    _, local_bindings, local_stars = module_scope(ast.Module(body=upgrade.body, type_ignores=[]))
    if local_stars:
        return []
    params = upgrade.args
    parameter_names = {arg.arg for arg in (*params.posonlyargs, *params.args, *params.kwonlyargs)}
    parameter_names.update(arg.arg for arg in (params.vararg, params.kwarg) if arg)
    op_names, sqlalchemy_names, column_names = set(), set(), set()
    sources = {("alembic", "op"): op_names, ("sqlalchemy", "Column"): column_names}
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports = ((alias, sqlalchemy_names) for alias in node.names if alias.name == "sqlalchemy")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imports = ((alias, sources[(node.module, alias.name)]) for alias in node.names
                       if (node.module, alias.name) in sources)
        else:
            continue
        for alias, names in imports:
            local = alias.asname or alias.name
            if bindings[local] == 1 and not local_bindings[local] and local not in parameter_names:
                names.add(local)

    operations = []
    for statement in upgrade.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            continue
        call = statement.value
        method = call.func
        if (not isinstance(method, ast.Attribute) or not isinstance(method.value, ast.Name)
                or method.value.id not in op_names):
            continue
        if method.attr == "drop_column":
            arguments = _arguments(call, ("table_name", "column_name"))
            if arguments is None:
                continue
            table = _table_name(arguments)
            name = _literal_name(arguments.get("column_name"))
            if table and name:
                operations.append((call.lineno, f"컬럼 삭제 {table}.{name}"))
        elif method.attr == "add_column":
            arguments = _arguments(call, ("table_name", "column"))
            if arguments is None:
                continue
            table = _table_name(arguments)
            column = arguments.get("column")
            if table and isinstance(column, ast.Call):
                description = _added_column(table, column, sqlalchemy_names, column_names)
                if description:
                    operations.append((call.lineno, description))
        elif method.attr == "alter_column":
            arguments = _arguments(call, ("table_name", "column_name"))
            if arguments is not None:
                description = _altered_column(arguments)
                if description:
                    operations.append((call.lineno, description))
    return operations


def _altered_column(arguments):
    table = _table_name(arguments)
    name = _literal_name(arguments.get("column_name"))
    if not table or not name:
        return None
    notes = []
    type_node = arguments.get("type_")
    if type_node is not None and not (isinstance(type_node, ast.Constant) and type_node.value is None):
        notes.append(f"타입 선언 · {ast.unparse(type_node)}")
    nullable = arguments.get("nullable")
    if isinstance(nullable, ast.Constant) and type(nullable.value) is bool:
        notes.append("NULL 허용" if nullable.value else "NULL 불허")
    default = arguments.get("server_default")
    if default is not None:
        if isinstance(default, ast.Constant) and default.value is None:
            notes.append("server_default 제거")
        elif not (isinstance(default, ast.Constant) and default.value is False):
            notes.append(f"server_default 선언 · {ast.unparse(default)}")
    rename = arguments.get("new_column_name")
    if rename is not None and not (isinstance(rename, ast.Constant) and rename.value is None):
        new_name = _literal_name(rename)
        if not new_name:
            return None
        notes.append(f"새 컬럼명 · {new_name}")
    if not notes:
        return None
    existing_type = arguments.get("existing_type")
    if existing_type is not None:
        notes.append(f"기존 타입 선언 · {ast.unparse(existing_type)}")
    return f"컬럼 변경 {table}.{name} ({', '.join(notes)})"


def _added_column(table, column, sqlalchemy_names, column_names):
    func = column.func
    if isinstance(func, ast.Name):
        recognized = func.id in column_names
    else:
        recognized = (isinstance(func, ast.Attribute) and func.attr == "Column"
                      and isinstance(func.value, ast.Name) and func.value.id in sqlalchemy_names)
    if not recognized or any(isinstance(arg, ast.Starred) for arg in column.args):
        return None
    keywords = {keyword.arg: keyword.value for keyword in column.keywords}
    if None in keywords:
        return None
    name = _literal_name(column.args[0] if column.args else keywords.get("name"))
    if not name:
        return None
    notes = []
    nullable = keywords.get("nullable")
    if isinstance(nullable, ast.Constant) and type(nullable.value) is bool:
        notes.append("NULL 허용" if nullable.value else "NULL 불허")
    default = keywords.get("server_default")
    if default is None:
        notes.append("server_default 지정 없음")
    elif isinstance(default, ast.Constant) and default.value is None:
        notes.append("server_default=None 명시")
    else:
        notes.append("server_default 표현식 지정")
    return f"컬럼 추가 {table}.{name} ({', '.join(notes)})"
