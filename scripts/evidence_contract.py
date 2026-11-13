"""저장소 관찰 사실·설정 단서·사용자 요구·시스템 가정·미확인 조건의 공통 계약.

관찰한 소스의 정적 근거만 기록합니다. 거짓 수치 confidence를 발명하지 않습니다.
원문 소스코드, 비밀정보 및 실행 결과를 외부로 전송하지 않습니다.
"""
from datetime import datetime, timezone

MAX_OBSERVATIONS = 300
MAX_UNKNOWN_QUESTIONS = 24

SIGNAL_EVIDENCE = {
    "api_routes": "api_routes",
    "nextjs": "next_configs",
    "next_static_export": "next_configs",
    "relational_database": "database_engine_evidence",
    "document_database": "database_engine_evidence",
    "authentication_library": "auth_dependency_paths",
    "background_job_library": "job_dependency_paths",
    "docker": "infrastructure_paths",
    "serverless_config": "infrastructure_paths",
    "mobile": None,
}
# 런타임에서 검증하지 않은 정적 탐지는 근거의 '관찰'과 의미 해석을 분리합니다.
INPUT_PROMPTS = (
    ("average_rps", "평균 초당 요청 수(RPS)는 어느 정도인가요?"),
    ("peak_rps", "최대 부하 시 피크 RPS는 어느 정도인가요?"),
    ("peak_concurrent_connections", "피크 동시 연결 수는 어느 정도인가요?"),
    ("expected_monthly_requests", "월간 요청 건수를 예상할 수 있나요?"),
    ("latency_target_ms", "허용 가능한 API 응답 지연 목표(ms)가 있나요?"),
    ("availability_target_percent", "목표 가용성(SLO)은 어느 정도인가요?"),
    ("region", "AWS 배포 리전과 데이터 저장 지역 제약은 무엇인가요?"),
    ("rto_minutes", "장애 발생 시 목표 복구시간(RTO, 분)은 얼마인가요?"),
    ("rpo_minutes", "목표 데이터 복구시점(RPO, 분)은 얼마인가요?"),
    ("monthly_budget_usd", "월간 인프라 예산 상한(USD)은 얼마인가요?"),
    ("operations_preference", "운영 우선순위는 최소 관리/균형/고가용성 중 무엇인가요?"),
    ("data_access_pattern", "데이터 접근 유형(관계형 트랜잭션/문서 조회/키 기반 조회)은 무엇인가요?"),
)


def build_evidence_contract(profile, graph, requirements, explicit_fields=(), architecture=None):
    explicit = set(explicit_fields)
    observations = []
    inferences = []
    unknowns = []

    def add_observation(category, value, path=None, line=None, certainty="static_observed", **details):
        if len(observations) >= MAX_OBSERVATIONS:
            return
        observations.append({
            "id": "F" + str(len(observations) + 1).zfill(4),
            "category": category, "value": value,
            "certainty": certainty,
            "source": {"path": path, "line": line, "method": (
                "ast" if certainty == "static_observed" else "configuration")},
            "runtime_verified": False, **details,
        })

    for manifest in sorted(profile.get("manifests", []), key=lambda v: (v["path"], v["technology"])):
        add_observation("configuration", manifest["technology"],
                        path=manifest["path"], certainty="configuration_observed")

    evidence = profile.get("evidence", {})
    for dependency in evidence.get("dependency_sources", []):
        add_observation("dependency", dependency["name"], path=dependency["path"],
                        certainty="configuration_observed")

    # AST에서 직접 파싱한 라우트/모델/호출만 코드 사실로 노출합니다.
    # 임의 파일명 기반 경로 유추는 같은 확실성을 부여하지 않습니다.
    for node in sorted(graph.get("nodes", []), key=lambda n: n.get("id", "")):
        if node.get("type") in ("route", "model"):
            details = {key: node[key] for key in ("route_scope", "prefix_source", "model_kind") if key in node}
            add_observation("ast_" + node["type"], node["name"],
                            path=node["path"], line=node["line"], **details)
    for edge in sorted(graph.get("edges", []), key=lambda e: (
        e.get("type", ""), e.get("source", ""), e.get("target", ""),
    )):
        if edge.get("type") == "calls":
            info = edge.get("evidence", {})
            add_observation("ast_call", "정적 호출 관계: " + edge["source"] + " → " + edge["target"],
                            path=info.get("path"), line=info.get("line"))

    for name in sorted(SIGNAL_EVIDENCE):
        if profile.get("signals", {}).get(name) is not True:
            continue
        source_key = SIGNAL_EVIDENCE[name]
        links = list(evidence.get(source_key, [])) if source_key else []
        if name in ("relational_database", "document_database"):
            dependency_key = ("relational_dependency_paths" if name == "relational_database"
                              else "document_dependency_paths")
            links.extend(evidence.get(dependency_key, []))
        if name == "api_routes":
            links.extend(route["path"] for route in evidence.get("ast_api_routes", []))
        inferences.append({
            "id": "I" + str(len(inferences) + 1).zfill(4),
            "signal": name,
            "value": True,
            "certainty": "configuration_indicator",
            "source_paths": sorted({x for x in links if isinstance(x, str)})[:10],
            "runtime_verified": False,
            "note": "설정/파일 경로 탐지 단서이며 실제 기능 구현 또는 운영 사용 여부는 미확인",
        })

    user_requirements = [
        {"id": "R" + str(i).zfill(4), "key": key, "value": requirements[key],
         "source": "explicit_user_input"}
        for i, key in enumerate(sorted(explicit & set(requirements)), 1)
    ]
    defaults = [
        {"key": key, "value": requirements[key], "source": "system_default_not_user_input"}
        for key in sorted(set(requirements) - explicit)
    ]
    def missing(key, question, reason="repository_cannot_prove"):
        if len(unknowns) < MAX_UNKNOWN_QUESTIONS and key not in {x["key"] for x in unknowns}:
            unknowns.append({
                "id": "U" + str(len(unknowns) + 1).zfill(4),
                "key": key, "question": question, "reason": reason,
                "status": "unknown", "requires_user_answer": True,
            })

    for key, question in INPUT_PROMPTS:
        if key not in explicit:
            missing(key, question, "not_provided")
    if requirements.get("data_classification") == "unknown":
        missing("data_classification", "어떤 등급의 데이터(공개/내부/민감)를 처리하나요?",
                "unknown_classification")
    # 코드에 인증 패키지나 DB 패키지 단서가 있으면 중복 질문하지 않습니다.
    # 미발견일 때는 서비스의 해당 기능 '부재'라고 확정하지 않습니다.
    signals = profile.get("signals", {})
    if "requires_authentication" not in explicit and signals.get("authentication_library") is not True:
        missing("requires_authentication", "로그인과 권한 통제가 필요한 서비스인가요?",
                "authentication_not_confirmed")
    if not ({"requires_relational_database", "requires_persistent_storage"} & explicit) and not (
        signals.get("relational_database") or signals.get("document_database")
    ):
        missing("database_requirement", "관계형/문서형 DB 또는 외부 SaaS 저장소가 필요한가요?",
                "database_not_confirmed")
    if signals.get("document_database") is True and "document_database_strategy" not in explicit:
        missing("document_database_strategy",
                "현재 문서형 DB를 유지하나요, AWS에서 다른 데이터 서비스를 검토하나요?",
                "document_database_migration_not_decided")
    if signals.get("nextjs") and not signals.get("next_static_export") and "rendering_mode" not in explicit:
        missing("rendering_mode", "Next.js에서 SSR·서버 액션·정적 export 중 무엇을 사용하나요?",
                "runtime_rendering_not_confirmed")
    if (graph.get("errors") or graph.get("scan_truncated") or
            graph.get("unresolved_routes") or profile.get("scan_truncated")):
        # 부분 파싱 실패는 사용자 질문으로 숨기지 않고 분석 범위 메타데이터에 명시합니다.
        parse_incomplete = True
    else:
        parse_incomplete = False

    assumptions = []
    if architecture:
        assumptions.append({
            "id": "A0001", "category": "proposed_architecture",
            "statement": "선택된 AWS 패턴은 런타임/계정 실측이 아닌 참조 설계 제안입니다.",
            "value": architecture["option_id"], "verified": False,
        })
    if "environment" not in explicit:
        assumptions.append({
            "id": "A0002", "category": "default",
            "statement": "개발 환경(dev)은 파일에 입력된 요구사항이 아니라 시스템 기본값입니다.",
            "value": requirements.get("environment", "dev"), "verified": False,
        })

    return {
        "schema_version": "1.0",
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "static_repository_evidence_and_explicit_requirements",
        "status": "partial" if parse_incomplete else "static_only",
        "observations": observations,
        "configuration_inferences": inferences,
        "user_requirements": user_requirements,
        "system_defaults": defaults,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "questions": [x["question"] for x in unknowns],
        "coverage": {
            "source_files_scanned": graph.get("scanned_source_files", 0),
            "source_files_parsed": graph.get("parsed_source_files", 0),
            "graph_parser_errors": len(graph.get("errors", [])),
            "unresolved_routes": len(graph.get("unresolved_routes", [])),
            "graph_scan_truncated": bool(graph.get("scan_truncated", False)),
            "manifest_scan_truncated": bool(profile.get("scan_truncated", False)),
            "observations_truncated": len(observations) >= MAX_OBSERVATIONS,
            "unsupported": [
                "DI, dynamic imports, runtime DB/API calls and actual traffic",
                "actual network, IAM, AZ and cloud pricing state",
            ],
        },
        "limitations": [
            "관측 사실은 정적 코드/설정 파일에 한정되고 실제 트래픽/호출 실행을 입증하지 않습니다.",
            "미탐지 신호는 해당 기능이 없다는 사실을 뜻하지 않습니다.",
            "신뢰도를 근거 없이 숫자로 추정하지 않고 static_observed / configuration_indicator로 구분합니다.",
            "파일 경로와 정적 코드 구조는 사용자 보고서에만 저장하며 외부 LLM에 원본을 전송하지 않습니다.",
        ],
    }


def markdown_evidence(contract):
    out = [
        "# 코드 근거 및 요구사항 확인", "",
        "> 사실(코드 관찰) / 설정 단서(추정) / 사용자 입력 / 기본값 / 설계 가정 / 미확인을 분리합니다.",
        "", "- 분석 시각(UTC): " + contract["analyzed_at_utc"],
        "- 분석 상태: " + contract["status"],
        "- 확인된 정적 근거: " + str(len(contract["observations"])) + "개",
        "- 정적으로 해석하지 못한 라우팅 단서: " + str(contract["coverage"]["unresolved_routes"]) + "개",
        "- 설정 기반 탐지 단서: " + str(len(contract["configuration_inferences"])) + "개",
        "- 명시적 사용자 요구사항: " + str(len(contract["user_requirements"])) + "개", "",
        "## 1. 코드/설정에서 확인된 근거", "",
    ]
    for item in contract["observations"][:70]:
        path = item["source"]["path"] or "(경로 없음)"
        line = ":" + str(item["source"]["line"]) if item["source"]["line"] else ""
        scope = {"router_local": " [라우터 내부 경로 · 앱 등록 경로 미확인]",
                 "app_local": " [앱 내부 경로]"}.get(item.get("route_scope"), "")
        if item.get("model_kind") == "sqlmodel_table":
            scope = " [SQLModel 테이블 선언]"
        out.append("- " + item["id"] + " [" + item["certainty"] + "] " +
                   str(item["value"]).replace("\n", " ") + scope + " (" + path + line + ")")
    if not contract["observations"]:
        out.append("- 정적 분석으로 확인된 근거가 없습니다.")
    out += ["", "## 2. 기술 단서 (런타임 동작 여부 미확인)", ""]
    for item in contract["configuration_inferences"]:
        out.append("- " + item["id"] + " " + item["signal"] +
                   " (확인 경로: " + ", ".join(item["source_paths"][:5]) + ")")
    if not contract["configuration_inferences"]:
        out.append("- 구성 요소 탐지 근거가 부족합니다.")
    out += ["", "## 3. 사용자 입력과 기본값", ""]
    for item in contract["user_requirements"]:
        out.append("- [사용자] " + item["key"] + " = " + str(item["value"]))
    for item in contract["system_defaults"]:
        out.append("- [기본값, 사용자의 선택 아님] " + item["key"] + " = " + str(item["value"]))
    out += ["", "## 4. 설계 가정 및 미검증 조건", ""]
    for item in contract["assumptions"]:
        out.append("- " + item["id"] + ": " + item["statement"])
    out += ["", "## 5. 사용자가 추가 입력하면 좋은 항목", ""]
    for item in contract["unknowns"]:
        out.append("- " + item["id"] + " / " + item["key"] + ": " + item["question"])
    if not contract["unknowns"]:
        out.append("- 현 단계에서 정의한 필수 추가 질문이 없습니다. 실환경 검증은 별도입니다.")
    if contract["status"] == "partial":
        out += ["", "**주의:** 일부 코드나 라우팅을 확인하지 못했습니다. 미관찰 항목을 부재로 단정할 수 없습니다."]
    out += ["", "## 6. 한계", ""]
    out.extend("- " + x for x in contract["limitations"])
    return "\n".join(out) + "\n"
