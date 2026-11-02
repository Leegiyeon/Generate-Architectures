"""읽기 전용 Python AST + Babel AST 분석 결과를 통합하는 애플리케이션 그래프.

확인된 구문만 노드/간선으로 기록합니다. 호출 대상이 모호하면 연결하지 않습니다.
사용자 소스코드를 실행하거나 외부 서비스에 전송하지 않습니다.
"""
import ast
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
from collections import Counter

try:
    from .repository_analyzer import EXCLUDED
except ImportError:
    from repository_analyzer import EXCLUDED

SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
PYTHON = {".py"}
IGNORE = {"test", "tests", "__tests__", "__mocks__", "fixtures", "node_modules"}
MAX_SOURCE_FILES = 300
MAX_SOURCE_BYTES = 65536
MAX_NODES = 2000
MAX_EDGES = 4000
HTTP = {"get", "post", "put", "patch", "delete", "options", "head"}


def _files(root):
    results = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in (EXCLUDED | IGNORE)
                         and not d.startswith(".") and not (Path(current) / d).is_symlink())
        for name in sorted(files):
            if len(results) >= MAX_SOURCE_FILES:
                return results, True
            target = Path(current) / name
            if target.suffix.lower() not in SUPPORTED or target.is_symlink():
                continue
            try:
                if not target.is_file() or target.stat().st_size > MAX_SOURCE_BYTES:
                    continue
            except OSError:
                continue
            results.append(target.relative_to(root).as_posix())
    return results, False


def _attr(expr):
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        base = _attr(expr.value)
        return base + "." + expr.attr if base else None
    return None


def _str(expr):
    return expr.value if isinstance(expr, ast.Constant) and isinstance(expr.value, str) else None


def _parse_python(root, p):
    source = (root / p).read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=p)
    imported, declarations, calls, routes, models = [], [], [], [], []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for name in node.names:
                imported.append({"module": name.name, "bindings": [{
                    "local": name.asname or name.name.split(".")[0], "imported": "*"}], "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            imported.append({
                "module": "." * node.level + (node.module or ""),
                "bindings": [{"local": n.asname or n.name, "imported": n.name} for n in node.names],
                "line": node.lineno,
            })

    def function(node, qualifier=""):
        name = qualifier + node.name
        declarations.append({"name": name, "kind": "method" if qualifier else "function", "line": node.lineno})
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            dotted = _attr(decorator.func)
            parts = dotted.split(".") if dotted else []
            if len(parts) == 2 and parts[1].lower() in HTTP and parts[0] in ("app", "router", "api"):
                url = _str(decorator.args[0]) if decorator.args else None
                if url and len(url) <= 160:
                    routes.append({"method": parts[1].upper(), "path": url, "line": decorator.lineno,
                                   "handler": name})
        # 호출 이름만 확인합니다. 동적 호출·리플렉션·의존성 주입은 해석하지 않습니다.
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee = _attr(child.func)
                if callee and len(callee) <= 160:
                    calls.append({"caller": name, "callee": callee, "line": child.lineno})

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function(node)
        elif isinstance(node, ast.ClassDef):
            bases = {_attr(b) for b in node.bases}
            if bases & {"Base", "models.Model", "Model", "db.Model"}:
                models.append({"name": node.name, "line": node.lineno})
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function(child, qualifier=node.name + ".")
    return {"path": p, "language": "python", "functions": declarations,
            "imports": imported, "calls": calls, "routes": routes, "models": models}


def _prisma_models(root):
    models=[]
    for candidate in (root / "prisma/schema.prisma", root / "schema.prisma"):
        if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size <= MAX_SOURCE_BYTES:
            for index, line in enumerate(candidate.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                stripped=line.strip()
                if stripped.startswith("model ") and stripped.endswith("{"):
                    name=stripped[6:-1].strip()
                    if name.isidentifier() and len(name)<=80:
                        models.append({"path":candidate.relative_to(root).as_posix(),"name":name,"line":index})
    return models


def _parse_js(root, paths):
    if not paths:
        return [], []
    executable = Path(__file__).parent / "js_analyzer/analyze.cjs"
    payload = json.dumps({"root": str(root), "files": paths})
    try:
        process = subprocess.run(["node", str(executable)], input=payload, text=True,
                                 capture_output=True, timeout=35, check=True)
        value=json.loads(process.stdout)
        return value["files"], value["errors"]
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
        return [], [{"path":"(JavaScript/TypeScript)", "kind":"parser_unavailable",
                     "message":"Node.js 또는 @babel/parser를 확인하세요. JS/TS 분석은 완료되지 않았습니다."}]


def _imported_path(path, spec, files):
    """확인 가능한 로컬 파일만 연결. tsconfig alias·동적 import는 미지원."""
    if not spec.startswith("."):
        return None
    base=PurePosixPath(path).parent.joinpath(spec)
    pieces=[]
    for part in base.parts:
        if part=="..":
            if not pieces:
                return None
            pieces.pop()
        elif part!=".":
            pieces.append(part)
    base="/".join(pieces)
    choices=[base]+[base + ext for ext in SUPPORTED]+[
        base + "/index" + ext for ext in SUPPORTED]
    return next((p for p in choices if p in files), None)


def _python_module_path(path, spec, names):
    if spec.startswith("."):
        count=len(spec)-len(spec.lstrip("."))
        package=path[:-3].replace("/", ".").split(".")[:-1]
        prefix=package[:max(0,len(package)-count+1)]
        mod=".".join(prefix + ([spec[count:]] if spec[count:] else []))
    else:
        mod=spec
    return names.get(mod) or names.get("src."+mod) or names.get(mod.removeprefix("src."))


def build_application_graph(repo):
    root=Path(repo).resolve()
    if not root.is_dir():
        raise ValueError("저장소 경로가 존재하지 않습니다.")
    files,truncated=_files(root)
    py_files=[p for p in files if p.endswith(".py")]
    js_files=[p for p in files if not p.endswith(".py")]
    parsed=[]
    errors=[]
    for p in py_files:
        try:
            parsed.append(_parse_python(root,p))
        except (SyntaxError, UnicodeError, OSError, ValueError) as exc:
            errors.append({"path":p,"kind":"parse_failed","message":type(exc).__name__})
    js_parsed,js_errors=_parse_js(root,js_files)
    parsed.extend(js_parsed)
    errors.extend(js_errors)
    parsed.sort(key=lambda item:item["path"])
    actual_files={p["path"] for p in parsed}
    modules={}
    for p in py_files:
        key=p[:-3].replace("/", ".")
        if key.endswith(".__init__"):
            key=key[:-9]
        modules[key]=p

    nodes={}
    edges={}
    def node(identifier,kind,label,path,line,language=""):
        if len(nodes)>=MAX_NODES or identifier in nodes: return
        nodes[identifier]={"id":identifier,"type":kind,"name":label,"path":path,
                           "line":int(line),"language":language,
                           "evidence":{"path":path,"line":int(line),"origin":"ast"}}
    def edge(src,dst,kind,path,line):
        if len(edges)>=MAX_EDGES or src not in nodes or dst not in nodes: return
        key=(src,dst,kind,path,int(line))
        edges[key]={"source":src,"target":dst,"type":kind,
                    "evidence":{"path":path,"line":int(line),"origin":"ast"}}

    symbols={}
    for info in parsed:
        p=info["path"]
        file_id="file:"+p
        node(file_id,"module",p,p,1,info["language"])
        for f in info["functions"]:
            key=(p,f["name"])
            fid="function:"+p+":"+f["name"]
            symbols[key]=fid
            node(fid,"function",f["name"],p,f["line"],info["language"])
            edge(file_id,fid,"defines",p,f["line"])
        for m in info.get("models",[]):
            mid="model:"+p+":"+m["name"]
            node(mid,"model",m["name"],p,m["line"],info["language"])
            edge(file_id,mid,"defines",p,m["line"])
    for m in _prisma_models(root):
        p=m["path"]
        file_id="file:"+p
        node(file_id,"module",p,p,1,"prisma")
        mid="model:"+p+":"+m["name"]
        node(mid,"model",m["name"],p,m["line"],"prisma")
        edge(file_id,mid,"defines",p,m["line"])

    for info in parsed:
        p=info["path"]
        alias={}
        for imp in info["imports"]:
            spec=imp["module"]
            target=_python_module_path(p,spec,modules) if info["language"]=="python" else _imported_path(p,spec,actual_files)
            # Python 'from app import service' / 'from . import service'는 추가 모듈을 가리킬 수 있습니다.
            if info["language"]=="python" and not target:
                continue
            if target and target in actual_files and target!=p:
                edge("file:"+p,"file:"+target,"imports",p,imp["line"])
            for binding in imp["bindings"]:
                local=binding["local"]
                original=binding["imported"]
                if not target or target not in actual_files:
                    if info["language"]=="python":
                        sub=_python_module_path(p,spec.lstrip(".")+"."+original,modules)
                        if sub in actual_files:
                            alias[local]=(sub,None)
                    continue
                if original=="*":
                    alias[local]=(target,None)
                elif original=="default":
                    alias[local]=(target,"default")
                else:
                    alias[local]=(target,original)
                # 파일 자체 import는 파일 단위 의존성, 호출은 실제 심볼 확인 후에만 연결.
        for item in info["calls"]:
            caller=symbols.get((p,item["caller"]))
            if not caller: continue
            callee=item["callee"]
            direct=symbols.get((p,callee))
            if direct:
                edge(caller,direct,"calls",p,item["line"])
                continue
            parts=callee.split(".")
            resolved=alias.get(parts[0])
            if not resolved: continue
            target,imported=resolved
            symbol=imported if imported not in (None,"*","default") else ""
            if len(parts)>1:
                symbol=".".join([symbol]+parts[1:]).lstrip(".")
            if symbol:
                dst=symbols.get((target,symbol))
                if dst: edge(caller,dst,"calls",p,item["line"])
        for route in info["routes"]:
            method=route["method"]
            url=route["path"]
            line=route["line"]
            rid="route:"+p+":"+str(line)+":"+method
            node(rid,"route",method+" "+url,p,line,info["language"])
            edge("file:"+p,rid,"defines",p,line)
            handler=symbols.get((p,route.get("handler") or ""))
            if handler: edge(rid,handler,"handles",p,line)

    results={
        "schema_version":"1.0",
        "analysis_mode":"static_ast_read_only",
        "scanned_source_files":len(files),
        "parsed_source_files":len(parsed),
        "scan_truncated":truncated or len(nodes)>=MAX_NODES or len(edges)>=MAX_EDGES,
        "nodes":sorted(nodes.values(),key=lambda x:x["id"]),
        "edges":sorted(edges.values(),key=lambda x:(x["source"],x["target"],x["type"],x["evidence"]["line"])),
        "counts":{"nodes":dict(sorted(Counter(n["type"] for n in nodes.values()).items())),
                  "edges":dict(sorted(Counter(e["type"] for e in edges.values()).items()))},
        "errors":errors[:50],
        "limitations":[
            "정적 AST에서 직접 확인되는 파일/함수/API/모델과 명시적 호출만 연결합니다.",
            "의존성 주입, 동적 import, 인터페이스 구현, 런타임 DI, 외부 API/DB 실제 접근은 아직 분석하지 않습니다.",
            "Python 외부 모듈, JS/TS tsconfig alias, 동적 경로, 복잡한 메서드 체인은 호출 대상으로 확정하지 않습니다.",
            "모델 정의 발견이 운영 DB 구성이나 실제 데이터베이스 호출을 증명하지 않습니다.",
        ],
    }
    return results
