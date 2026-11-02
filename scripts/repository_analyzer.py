"""저장소 근거 수집: 제한된 설정 파일과 경로만 분석하며 소스 전문을 전송하지 않습니다."""
import json
import os
from pathlib import Path
import re

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
    "compose.yaml": ("Docker Compose", "containers"),
    "serverless.yml": ("Serverless", "serverless"),
    "app.json": ("Expo", "mobile"), "pubspec.yaml": ("Flutter", "mobile"),
    "main.tf": ("Terraform", "infra"),
}
MAX_FILES = 5000
MAX_BYTES = 65536
MAX_EVIDENCE = 100


def safe_text(path):
    """시크릿 파일, 심볼릭 링크 및 대용량 파일은 읽지 않습니다."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


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
    dependency_names = set()
    for m in manifests:
        p = root / m["path"]
        if p.name != "package.json":
            continue
        try:
            package = json.loads(safe_text(p))
            if not isinstance(package, dict):
                continue
            for field in ("dependencies", "devDependencies"):
                if isinstance(package.get(field), dict):
                    dependency_names.update(package[field])
        except (ValueError, TypeError):
            pass
    if "next" in dependency_names:
        next_present = True
    if "vite" in dependency_names and not any(m["technology"] == "Vite" for m in manifests):
        manifests.append({"path": "package.json", "technology": "Vite", "category": "web"})
    if next_present and not any(m["technology"] == "Next.js" for m in manifests):
        manifests.append({"path": "package.json", "technology": "Next.js", "category": "web"})

    api_files = [p for p in filenames if (
        ("/api/" in "/" + p and p.endswith((".ts", ".tsx", ".js", ".py", ".go"))) or
        (p.endswith("/route.ts") or p.endswith("/route.js")) and
        ("/app/" in "/" + p or p.startswith("app/")))]
    db_files = [p for p in filenames if p.endswith(("prisma/schema.prisma", "schema.prisma")) or
                "/migrations/" in "/" + p or p.startswith("migrations/")]
    infra_files = [p for p in filenames if p.endswith(".tf") or p in
                   ("Dockerfile", "docker-compose.yml", "compose.yaml", "serverless.yml")]
    auth_deps = {"next-auth", "@auth/core", "@clerk/nextjs", "passport",
                 "aws-amplify", "amazon-cognito-identity-js"}
    database_deps = {"prisma", "@prisma/client", "pg", "mysql2", "mongoose",
                     "sequelize", "typeorm", "drizzle-orm", "better-sqlite3"}
    queue_deps = {"bullmq", "bull", "amqplib", "ioredis"}
    techs = sorted({m["technology"] for m in manifests})
    categories = {m["category"] for m in manifests}
    signals = {
        "api_routes": bool(api_files),
        "nextjs": next_present,
        "next_static_export": bool(next_export),
        "relational_database": bool(db_files or database_deps.intersection(dependency_names)),
        "authentication_library": bool(auth_deps.intersection(dependency_names)),
        "background_job_library": bool(queue_deps.intersection(dependency_names)),
        "docker": "containers" in categories,
        "serverless_config": "serverless" in categories,
        "mobile": "mobile" in categories,
    }
    evidence_map = {
        "api_routes": evidence(api_files),
        "database_paths": evidence(db_files),
        "infrastructure_paths": evidence(infra_files),
        "auth_dependencies": sorted(auth_deps & dependency_names),
        "db_dependencies": sorted(database_deps & dependency_names),
        "job_dependencies": sorted(queue_deps & dependency_names),
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
    if not signals["relational_database"]:
        questions.append("영속 데이터 저장소가 필요한가요? 기존 DB 또는 외부 SaaS가 있나요?")
    if not signals["authentication_library"]:
        questions.append("사용자 인증·인가가 필요한가요? 기존 인증 제공자가 있나요?")
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
            "코드 내부의 실제 DB 연결 및 인프라 배포 상태는 별도 검증이 필요합니다.",
        ],
    }
