"""저장소 근거 수집: 제한된 설정 파일과 경로만 분석하며 소스 전문을 전송하지 않습니다."""
import json
import os
from pathlib import Path
import re
import tomllib
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

EXCLUDED = frozenset({".git", ".github", "node_modules", ".next", "dist", "build",
                      ".venv", "venv", "__pycache__", "coverage", "vendor",
                      ".terraform", ".idea", ".cache", "target"})
MANIFESTS = {
    "package.json": ("Node.js", "web"), "next.config.js": ("Next.js", "web"),
    "next.config.mjs": ("Next.js", "web"), "next.config.ts": ("Next.js", "web"),
    "vite.config.ts": ("Vite", "web"), "vite.config.js": ("Vite", "web"),
    "vite.config.mts": ("Vite", "web"), "requirements.txt": ("Python", "backend"),
    "pyproject.toml": ("Python", "backend"), "go.mod": ("Go", "backend"),
    "pom.xml": ("Java", "backend"), "Dockerfile": ("Docker", "containers"),
    "docker-compose.yml": ("Docker Compose", "containers"),
    "docker-compose.yaml": ("Docker Compose", "containers"),
    "compose.yml": ("Docker Compose", "containers"),
    "compose.yaml": ("Docker Compose", "containers"),
    "serverless.yml": ("Serverless", "serverless"),
    "app.json": ("Expo", "mobile"), "pubspec.yaml": ("Flutter", "mobile"),
    "main.tf": ("Terraform", "infra"),
}
MAX_FILES = 5000
MAX_BYTES = 65536
MAX_EVIDENCE = 100
TEST_DIRECTORIES = frozenset({"test", "tests", "__tests__", "__mocks__",
                              "fixtures", "__fixtures__"})
PYTHON_DATABASE_DEPS = frozenset({"sqlmodel", "sqlalchemy", "psycopg", "psycopg2",
    "psycopg2-binary", "asyncpg", "pymysql", "mysqlclient", "mysql-connector-python", "aiosqlite"})
PYTHON_DOCUMENT_DEPS = frozenset({"pymongo", "motor"})
PYTHON_AUTH_DEPS = frozenset({"pyjwt", "python-jose", "authlib", "django-allauth"})


def is_test_source(relative):
    """표준 테스트 경로만 제외하며 test.ts 같은 실제 API 이름은 보존합니다."""
    path = Path(relative)
    stem = path.stem.lower()
    directories = [part.lower() for part in path.parts[:-1]]
    # Next.js app 경로의 test/tests/fixtures는 실제 URL 세그먼트일 수 있습니다.
    # 앱 바깥 테스트 루트와 명시적인 __tests__/__fixtures__는 계속 제외합니다.
    if path.name.lower() in ("route.ts", "route.js") and "app" in directories:
        app_index = directories.index("app")
        test_directory = (any(part in TEST_DIRECTORIES for part in directories[:app_index]) or
                          any(part.startswith("__") and part in TEST_DIRECTORIES
                              for part in directories[app_index + 1:]))
    else:
        test_directory = any(part in TEST_DIRECTORIES for part in directories)
    return (test_directory or
            bool(re.search(r"\.(?:test|spec)$", stem)) or
            path.suffix.lower() == ".py" and (stem.startswith("test_") or stem.endswith("_test")) or
            path.suffix.lower() == ".go" and stem.endswith("_test"))


def safe_text(path):
    """시크릿 파일, 심볼릭 링크 및 대용량 파일은 읽지 않습니다."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _python_requirement_name(value):
    """이름 있는 선언만 추출. marker/URL을 평가하거나 외부 파일을 따라가지 않습니다."""
    if not isinstance(value, str):
        return None
    declaration = value.split(" #", 1)[0].strip()
    if not declaration or declaration.startswith(("#", "-")):
        return None
    try:
        return canonicalize_name(Requirement(declaration).name)
    except InvalidRequirement:
        return None


def _python_dependency_names(path):
    text = safe_text(path)
    if path.name == "pyproject.toml":
        try:
            project = tomllib.loads(text).get("project", {})
            values = project.get("dependencies", []) if isinstance(project, dict) else []
        except (ValueError, TypeError):
            return set()
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            return set()
    else:
        values = text.replace("\\\n", "").splitlines()
    return {name for value in values if (name := _python_requirement_name(value))}


def inspect_repository(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("분석 경로가 디렉터리가 아닙니다.")
    manifests, filenames = [], []
    inspected = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and
                         not d.startswith(".") and not (Path(current) / d).is_symlink())
        for filename in sorted(files):
            if inspected >= MAX_FILES:
                break
            path = Path(current) / filename
            if path.is_symlink() or not path.is_file():
                continue
            inspected += 1
            relative = path.relative_to(root).as_posix()
            filenames.append(relative)
            if filename in MANIFESTS and len(manifests) < MAX_EVIDENCE:
                tech, category = MANIFESTS[filename]
                manifests.append({"path": relative, "technology": tech, "category": category})
        if inspected >= MAX_FILES:
            break

    def evidence(paths):
        return sorted(paths)[:20]

    paths = set(filenames)
    next_configs = [root / m["path"] for m in manifests if m["technology"] == "Next.js"]
    # 명시적인 next export 설정이 확인되기 전에는 SSR 가능성을 배제하지 않습니다.
    next_export = any(re.search(r"\boutput\s*:\s*['\"]export['\"]", safe_text(p))
                      for p in next_configs)
    next_present = bool(next_configs)
    dependency_names, python_names, dependency_sources = set(), set(), []
    for m in manifests:
        p = root / m["path"]
        if p.name in ("requirements.txt", "pyproject.toml"):
            names = _python_dependency_names(p)
            python_names.update(names)
            dependency_sources.extend({"name": name, "path": m["path"], "ecosystem": "python",
                                       "section": ("project.dependencies" if p.name == "pyproject.toml"
                                                   else "requirements")}
                                      for name in sorted(names))
            continue
        if p.name != "package.json":
            continue
        try:
            package = json.loads(safe_text(p))
            if not isinstance(package, dict):
                continue
            for field in ("dependencies", "devDependencies"):
                if isinstance(package.get(field), dict):
                    dependency_names.update(package[field])
                    dependency_sources.extend({"name": name, "path": m["path"],
                                               "ecosystem": "npm", "section": field}
                                              for name in sorted(package[field]))
        except (ValueError, TypeError):
            pass
    if "next" in dependency_names:
        next_present = True
    for name, technology, ecosystem, category in (
            ("vite", "Vite", "npm", "web"), ("next", "Next.js", "npm", "web"),
            ("@nestjs/core", "NestJS", "npm", "backend"),
            ("fastapi", "FastAPI", "python", "backend")):
        sources = [source for source in dependency_sources
                   if source["name"] == name and source["ecosystem"] == ecosystem]
        if sources and not any(m["technology"] == technology for m in manifests):
            manifests.append({"path": sources[0]["path"], "technology": technology, "category": category})

    api_files = [p for p in filenames if not is_test_source(p) and (
        ("/api/" in "/" + p and p.endswith((".ts", ".tsx", ".js", ".py", ".go"))) or
        (p.endswith("/route.ts") or p.endswith("/route.js")) and
        ("/app/" in "/" + p or p.startswith("app/")))]
    db_files = [p for p in filenames if p.endswith(("prisma/schema.prisma", "schema.prisma")) or
                "/migrations/" in "/" + p or p.startswith("migrations/")]
    infra_names = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                   "compose.yml", "compose.yaml", "serverless.yml"}
    infra_files = [p for p in filenames if p.endswith(".tf") or Path(p).name in infra_names]
    auth_deps = {"next-auth", "@auth/core", "@clerk/nextjs", "passport",
                 "aws-amplify", "amazon-cognito-identity-js"}
    database_deps = {"pg", "mysql2", "sequelize", "typeorm", "drizzle-orm", "better-sqlite3"}
    document_deps = {"mongoose", "mongodb"}
    queue_deps = {"bullmq", "bull", "amqplib", "ioredis"}
    relational = database_deps & dependency_names | PYTHON_DATABASE_DEPS & python_names
    document = document_deps & dependency_names | PYTHON_DOCUMENT_DEPS & python_names
    authentication = auth_deps & dependency_names | PYTHON_AUTH_DEPS & python_names
    jobs = queue_deps & dependency_names

    def dependency_paths(npm, python=()):
        return evidence({source["path"] for source in dependency_sources
                         if source["name"] in (npm if source["ecosystem"] == "npm" else python)})

    relational_paths = dependency_paths(database_deps, PYTHON_DATABASE_DEPS)
    document_paths = dependency_paths(document_deps, PYTHON_DOCUMENT_DEPS)
    relevant_npm = database_deps | document_deps | auth_deps | queue_deps | {"prisma", "@prisma/client", "next", "vite", "@nestjs/core"}
    relevant_python = PYTHON_DATABASE_DEPS | PYTHON_DOCUMENT_DEPS | PYTHON_AUTH_DEPS | {"fastapi"}
    # Prisma 스키마는 DB 엔진이 PostgreSQL/MySQL인지 MongoDB인지 구분해 확인합니다.
    prisma_files = [root / p for p in db_files if p.endswith("schema.prisma")]
    prisma_text = "\n".join(safe_text(p) for p in prisma_files[:5])
    prisma_relational = bool(re.search(r'provider\s*=\s*["\x27](postgresql|mysql|sqlite|sqlserver)["\x27]', prisma_text))
    prisma_document = bool(re.search(r'provider\s*=\s*["\x27]mongodb["\x27]', prisma_text))
    techs = sorted({m["technology"] for m in manifests})
    categories = {m["category"] for m in manifests}
    signals = {
        "api_routes": bool(api_files),
        "nextjs": next_present,
        "next_static_export": bool(next_export),
        "relational_database": bool(prisma_relational or relational),
        "document_database": bool(prisma_document or document),
        "authentication_library": bool(authentication),
        "background_job_library": bool(jobs),
        "docker": "containers" in categories,
        "serverless_config": "serverless" in categories,
        "mobile": "mobile" in categories,
    }
    evidence_map = {
        "api_routes": evidence(api_files),
        "database_paths": evidence(db_files),
        "infrastructure_paths": evidence(infra_files),
        "auth_dependencies": sorted(authentication),
        "db_dependencies": sorted(relational | document |
                                  {"prisma", "@prisma/client"} & dependency_names),
        "database_engine_evidence": ([p.relative_to(root).as_posix() for p in prisma_files] if
                                     prisma_relational or prisma_document else []),
        "relational_dependency_paths": relational_paths,
        "document_dependency_paths": document_paths,
        "auth_dependency_paths": dependency_paths(auth_deps, PYTHON_AUTH_DEPS),
        "job_dependency_paths": dependency_paths(queue_deps),
        "dependency_sources": [source for source in dependency_sources
                               if source["name"] in (relevant_npm if source["ecosystem"] == "npm"
                                                     else relevant_python)][:MAX_EVIDENCE],
        "job_dependencies": sorted(jobs),
        "next_configs": [p.relative_to(root).as_posix() for p in next_configs],
    }
    explicit_static = (
        next_present and next_export and not signals["api_routes"] or
        not next_present and "Vite" in techs and not signals["api_routes"] and
        "backend" not in categories
    )
    # 디렉터리 스캔으로 동적 렌더링 사용 여부를 증명할 수 없으므로 검토 사항으로 남깁니다.
    questions = []
    if next_present and not next_export:
        questions.append("Next.js SSR/서버 컴포넌트/서버 액션 사용 여부는 무엇인가요?")
    if not signals["relational_database"] and not signals["document_database"]:
        questions.append("영속 데이터 저장소가 필요한가요? 기존 DB 또는 외부 SaaS가 있나요?")
    if db_files and not prisma_relational and not prisma_document and not signals["relational_database"]:
        questions.append("ORM/마이그레이션 파일은 있으나 DB 엔진 유형은 확인되지 않았습니다.")
    if signals["document_database"]:
        questions.append("MongoDB 계열 DB를 계속 사용할 예정인가요? 호환 AWS 관리형 서비스 검토가 필요한가요?")
    if not signals["authentication_library"]:
        questions.append("알려진 인증 라이브러리는 확인되지 않았습니다. 자체 구현 또는 외부 인증·인가가 있나요? 필요한 인증 방식을 확인해주세요.")
    if inspected >= MAX_FILES:
        questions.append("파일 탐색 상한(5,000개)에 도달했습니다. 분석 제외 영역이 없는지 확인해주세요.")

    return {
        "schema_version": "1.0",
        "inspected_files": inspected,
        "scan_truncated": inspected >= MAX_FILES,
        "technologies": techs,
        "manifests": manifests[:MAX_EVIDENCE],
        "signals": signals,
        "evidence": evidence_map,
        "static_candidate": explicit_static,
        "questions": questions,
        "limitations": [
            "설정 파일 일부와 파일 경로만 분석하며 전체 함수 호출 및 실제 데이터 흐름은 추론하지 않습니다.",
            "Next.js의 SSR·서버 액션 부재는 자동으로 증명할 수 없습니다.",
            "인증 라이브러리 미탐지는 인증 부재를 뜻하지 않습니다. 자체 구현·외부 인증과 실제 인가 정책은 별도 확인이 필요합니다.",
            "코드 내부의 실제 DB 연결 및 인프라 배포 상태는 별도 검증이 필요합니다.",
            "Python 의존성은 requirements.txt의 이름 있는 선언과 pyproject.toml의 project.dependencies만 확인합니다. optional/dependency-groups/Poetry·동적 의존성, 포함 파일(-r/-c), 환경 marker 평가와 URL 조회는 지원하지 않습니다.",
        ],
    }
