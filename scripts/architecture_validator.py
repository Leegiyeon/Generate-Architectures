"""읽기 전용 아키텍처 정적 제약 검사. AWS 계정·가격·성능·보안은 검증하지 않습니다."""
from collections import Counter

try:
    from .architecture_advisor import TEMPLATES, PILLARS
except ImportError:
    from architecture_advisor import TEMPLATES, PILLARS

KNOWN_NODES = set().union(*(set(x["nodes"]) for x in TEMPLATES.values()))


def validate_architecture(architecture, profile, requirements, graph=None, ai_review=None):
    """명시적 상충·자료 무결성 오류는 blocker, 미측정은 review_required로 기록."""
    graph = graph or {}
    signals = profile.get("signals", {})
    choice = architecture.get("option_id")
    nodes = architecture.get("nodes", [])
    edges = architecture.get("edges", [])
    findings = []

    def add(rule_id, pillar, severity, title, detail, evidence, action):
        findings.append({
            "rule_id": rule_id, "pillar": pillar, "severity": severity,
            "title": title, "detail": detail, "evidence": evidence,
            "recommended_action": action,
            "verification": "정적 설계 충돌 검토: 운영 환경 검사 아님",
        })

    # 1. 설계 데이터 참조 무결성
    if choice not in TEMPLATES:
        add("ARC-001", "운영 우수성", "blocker", "지원되지 않는 배포 패턴",
            "등록되지 않은 설계 유형입니다.", ["architecture.option_id"], "배포 유형을 다시 검토하세요.")
    if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
        add("ARC-002", "운영 우수성", "blocker", "노드 목록 오류",
            "노드가 문자열 목록이 아닙니다.", ["architecture.nodes"], "노드 데이터를 수정하세요.")
        nodes = []
    if not isinstance(edges, list):
        add("ARC-003", "운영 우수성", "blocker", "연결 목록 오류",
            "연결이 목록 형식이 아닙니다.", ["architecture.edges"], "연결 데이터를 수정하세요.")
        edges = []
    if len(nodes) != len(set(nodes)) or set(nodes) - KNOWN_NODES:
        add("ARC-004", "운영 우수성", "blocker", "중복/미지원 서비스",
            "서비스 식별자가 지원 목록과 다릅니다.", ["architecture.nodes"], "노드 목록을 확인하세요.")
    valid_edges = [e for e in edges if isinstance(e, (list, tuple)) and len(e) == 2 and
                   all(isinstance(p, str) and p in nodes for p in e)]
    if len(valid_edges) != len(edges):
        add("ARC-005", "운영 우수성", "blocker", "존재하지 않는 연결 대상",
            "연결이 존재하지 않는 서비스 노드를 참조합니다.",
            ["architecture.edges", "architecture.nodes"], "간선의 양 끝점을 확인하세요.")
    if choice in TEMPLATES:
        template = TEMPLATES[choice]
        if not set(nodes).issubset(template["nodes"]):
            add("ARC-006", "운영 우수성", "blocker", "선택 패턴에 없는 서비스",
                "지원 템플릿에 없는 서비스가 포함되었습니다.",
                ["architecture.option_id", "architecture.nodes"], "템플릿의 노드를 확인하세요.")
        if any(tuple(e) not in template["edges"] for e in valid_edges):
            add("ARC-007", "운영 우수성", "blocker", "선택 패턴에 없는 연결",
                "템플릿에 없는 연결이 추가되었습니다.",
                ["architecture.option_id", "architecture.edges"], "서비스 간 연결을 확인하세요.")

    # 2. 코드의 존재 단서는 인정하되 미탐지는 기능 부재를 증명하지 않음
    relational = requirements.get("requires_relational_database")
    persistent = requirements.get("requires_persistent_storage")
    sql = signals.get("relational_database") is True
    document = signals.get("document_database") is True
    if relational is True and persistent is False:
        add("REQ-001", "안정성", "blocker", "영속 저장 요구사항 충돌",
            "관계형 DB가 필수지만 영속 저장소는 불필요하다고 명시되었습니다.",
            ["requirements.requires_relational_database", "requirements.requires_persistent_storage"],
            "상충하는 요구사항을 수정하세요.")
    if relational is False and sql:
        add("REQ-002", "운영 우수성", "review_required", "DB 요구와 코드 단서 불일치",
            "DB가 불필요하다는 요구와 관계형 DB 의존성이 서로 다릅니다.",
            ["requirements.requires_relational_database", "repository.signals.relational_database"],
            "DB 사용 여부를 확인하세요.")
    if persistent is False and (sql or document):
        add("REQ-003", "안정성", "review_required", "영속성 미사용 주장과 DB 단서",
            "DB 관련 코드가 남아 있어 영속 저장 불필요를 확신할 수 없습니다.",
            ["requirements.requires_persistent_storage", "repository.signals.relational_database",
             "repository.signals.document_database"], "실제 영속 저장 사용 여부를 확인하세요.")
    if choice == "static":
        if signals.get("api_routes") is True:
            add("PAT-001", "성능 효율성", "blocker", "정적 호스팅과 API 라우트",
                "서버 실행이 필요한 API 경로가 감지되었습니다.",
                ["architecture.option_id", "repository.signals.api_routes"],
                "별도의 API 실행 계층을 설계하세요.")
        if signals.get("nextjs") and not signals.get("next_static_export"):
            add("PAT-002", "성능 효율성", "blocker", "Next.js 정적 export 미확인",
                "SSR/서버 액션 사용 여부를 확인할 수 없습니다.",
                ["repository.signals.nextjs", "repository.signals.next_static_export"],
                "정적 export 설정 또는 SSR 필요성을 검증하세요.")
        if relational is True or sql or document or persistent is True:
            add("PAT-003", "안정성", "blocker", "정적 배포의 데이터 계층 누락",
                "DB/영속 저장 요구를 표현할 실행 계층이 없습니다.",
                ["requirements.requires_persistent_storage", "repository.signals.relational_database",
                 "repository.signals.document_database"], "데이터/API 계층을 별도 설계하세요.")
    if choice == "serverless" and (relational is True or sql):
        add("PAT-004", "안정성", "blocker", "서버리스 참조안과 관계형 DB 요구",
            "이 템플릿은 RDS 연결이 없어 기존 관계형 DB 전제를 충족하지 못합니다.",
            ["architecture.option_id", "requirements.requires_relational_database"],
            "관계형 DB를 포함하는 서버리스 패턴을 설계하세요.")
    if choice == "mobile" and requirements.get("workload") not in ("auto", "mobile"):
        add("PAT-005", "운영 우수성", "blocker", "모바일과 명시 워크로드 충돌",
            "사용자가 지정한 워크로드와 선택 패턴이 다릅니다.",
            ["requirements.workload", "architecture.option_id"], "워크로드를 확인하세요.")
    if choice == "mobile" and relational is True:
        add("PAT-006", "안정성", "blocker", "모바일 참조안의 관계형 DB 누락",
            "모바일 템플릿에는 관계형 DB 연결이 없습니다.",
            ["architecture.option_id", "requirements.requires_relational_database"],
            "관계형 DB를 유지할 별도 패턴을 설계하세요.")
    if choice == "containers" and relational is True and "Amazon RDS" not in nodes:
        add("PAT-007", "안정성", "blocker", "컨테이너 참조안의 관계형 DB 누락",
            "필수 관계형 DB 서비스 후보를 포함하지 않습니다.",
            ["requirements.requires_relational_database", "architecture.nodes"],
            "데이터 서비스 후보를 보강하세요.")

    # 3. 미측정 조건은 검증 필요로 표시. 안전성 합격을 선언하지 않음.
    if graph.get("errors") or graph.get("scan_truncated") or profile.get("scan_truncated"):
        add("EVD-001", "운영 우수성", "review_required", "분석 누락 확인 필요",
            "코드 파싱 오류 또는 분석량 제한으로 연결 관계가 누락되었을 수 있습니다.",
            ["application_graph.errors", "application_graph.scan_truncated",
             "repository.scan_truncated"], "미분석 파일과 구문을 검토하세요.")
    if requirements.get("data_classification") == "sensitive":
        add("SEC-001", "보안", "review_required", "민감정보 통제 미검증",
            "암호화, IAM, 키 관리, 로그의 민감정보 처리는 확인하지 않았습니다.",
            ["requirements.data_classification"], "실제 IaC/IAM과 조직 정책을 확인하세요.")
    if requirements.get("data_classification") == "unknown":
        add("SEC-002", "보안", "review_required", "데이터 민감도 미확정",
            "데이터 분류가 없어 보안 통제를 판단할 수 없습니다.",
            ["requirements.data_classification"], "데이터 등급을 지정하세요.")
    if requirements.get("requires_authentication") is True:
        add("SEC-003", "보안", "review_required", "인증·인가 실구현 미검증",
            "인증 필요가 입력되었지만 실제 인가/세션 정책은 확인하지 않았습니다.",
            ["requirements.requires_authentication"], "IAM·앱 인가·토큰 검증을 점검하세요.")
    if requirements.get("availability_target_percent", 0) >= 99.9:
        add("REL-001", "안정성", "review_required", "목표 가용성 검증 전",
            "AZ 이중화 및 장애 대응과 가용성 측정 결과를 확인하지 않았습니다.",
            ["requirements.availability_target_percent"], "실제 복구/가용성 테스트가 필요합니다.")
    if "rto_minutes" in requirements or "rpo_minutes" in requirements:
        add("REL-002", "안정성", "review_required", "복구 목표 검증 전",
            "RTO/RPO 입력이 있으나 백업/복원 실측 결과가 없습니다.",
            ["requirements.rto_minutes", "requirements.rpo_minutes"],
            "백업 주기, 복구 전략 및 훈련을 검토하세요.")
    if requirements.get("environment") == "production":
        add("OPS-001", "운영 우수성", "review_required", "운영 통제 미확인",
            "런북, 장애 알림, 변경 이력, 롤백 계획이 확인되지 않았습니다.",
            ["requirements.environment"], "상용 운영 준비 절차를 검토하세요.")
    if "expected_monthly_requests" in requirements:
        add("PERF-001", "성능 효율성", "review_required", "피크 처리량 미측정",
            "월 요청 수만으로 피크 RPS나 지연시간을 추정할 수 없습니다.",
            ["requirements.expected_monthly_requests"],
            "피크·동시 연결·지연 목표로 부하 테스트를 수행하세요.")
    if "monthly_budget_usd" in requirements:
        add("COST-001", "비용 최적화", "review_required", "예산 충족 여부 미산정",
            "AWS 가격표/리전별 요금과 자원 사용량을 조회하지 않았습니다.",
            ["requirements.monthly_budget_usd"], "가격·사용량 모델을 준비하세요.")
    if not requirements.get("region"):
        add("REQ-004", "운영 우수성", "review_required", "배포 리전 미확정",
            "데이터 보존 지역·가격·네트워크 지연을 판단할 리전 정보가 없습니다.",
            ["requirements.region"], "배포 리전과 데이터 지역 정책을 지정하세요.")

    counts = Counter(item["severity"] for item in findings)
    return {
        "schema_version": "1.0",
        "scope": "reference_design_static_consistency_only",
        "decision_gate": "blocked" if counts["blocker"] else "review_required",
        "production_ready": False,
        "aws_account_checked": False,
        "cost_estimated": False,
        "performance_tested": False,
        "security_compliance_verified": False,
        "selected_option": choice,
        "ai_review_status": (ai_review or {}).get("status", "disabled"),
        "ai_proposal_applied": False,
        "counts": {"blocker": counts["blocker"], "review_required": counts["review_required"]},
        "findings": sorted(findings, key=lambda f: (0 if f["severity"] == "blocker" else 1, f["rule_id"])),
        "well_architected": [{
            "name": pillar, "status": "검증 전",
            "finding_count": sum(1 for finding in findings if finding["pillar"] == pillar),
            "review_topic": description,
        } for pillar, description in PILLARS.items()],
        "limitations": [
            "차단은 이 참조안의 자동 채택 제한이지 AWS 기술 자체의 불가능 판정이 아닙니다.",
            "실제 AWS 정책, IAM, 데이터 암호화, AZ, 요금 및 성능을 검사하지 않았습니다.",
            "Well-Architected 6개 원칙은 실환경 검증 또는 전문가 검토가 필요합니다.",
            "AI 제안은 사실성 검증 없이 자동 승인하거나 배포하지 않습니다.",
        ],
    }


def markdown_validation(validation):
    lines = [
        "# 아키텍처 정적 제약 검토", "",
        "> **운영 적합성 검증 전.** AWS 계정·IAM·네트워크·비용·성능·가용성을 검사하지 않았습니다.",
        "",
        "**검토 상태:** " + ("자동 채택 차단" if validation["decision_gate"] == "blocked"
                         else "추가 검토 필요"),
        "",
        "- 차단 항목: " + str(validation["counts"]["blocker"]),
        "- 수동 검토 항목: " + str(validation["counts"]["review_required"]),
        "- AI 제안 자동 반영: 없음", "",
        "## 1. 발견된 충돌과 확인 필요 사항", "",
    ]
    for item in validation["findings"]:
        lines += [
            "### " + item["rule_id"] + " · " +
            ("자동 채택 차단" if item["severity"] == "blocker" else "수동 검토") +
            " · " + item["title"], "",
            item["detail"], "",
            "- 근거: " + ", ".join(item["evidence"]),
            "- 권장 조치: " + item["recommended_action"], "",
        ]
    if not validation["findings"]:
        lines.append("- 확인 가능한 충돌 없음. 실환경 적합성은 여전히 검증 전입니다.")
    lines += ["", "## 2. AWS Well-Architected 6개 원칙", "",
              "| 원칙 | 상태 | 남은 검토 |", "| --- | --- | --- |"]
    for item in validation["well_architected"]:
        lines.append("| " + item["name"] + " | 검증 전 | " + item["review_topic"] + " |")
    lines += ["", "## 3. 검증 범위의 한계", ""]
    lines.extend("- " + item for item in validation["limitations"])
    return "\n".join(lines) + "\n"


def markdown_adr(architecture, validation):
    """요구사항/코드 근거/제안/미승인 상태를 구분한 결정 기록."""
    decision = architecture["decision"]
    lines = [
        "# ADR-0001: AWS 참조 설계 선택 기록", "",
        "- 상태: **초안 / 승인 전**",
        "- 제안된 패턴: " + architecture["pattern"],
        "- 검토 게이트: " + validation["decision_gate"],
        "- 운영 적합성: **검증 전**", "",
        "## 1. 저장소에서 관찰된 사실", "",
    ]
    for e in architecture["evidence"][:30]:
        lines.append("- " + e["path"].replace("\n", " ") + ": " + e["technology"])
    if not architecture["evidence"]:
        lines.append("- 확인된 기술 설정 파일 없음")
    lines += ["", "## 2. 사용자가 명시한 요구사항", ""]
    for key, value in sorted(architecture["requirements"].items()):
        lines.append("- " + key + ": " + str(value))
    lines += ["", "## 3. 제안 패턴 선정 근거", ""]
    lines.extend("- " + reason for reason in decision["rationale"])
    lines += ["", "## 4. 배포 대안 비교", "",
              "| 대안 | 검토 후보 | 선택 | 주요 제약 |",
              "| --- | --- | --- | --- |"]
    for alt in decision["alternatives"]:
        lines.append("| " + alt["name"] + " | " +
                     ("가능" if alt["applicable"] else "현재 규칙상 제한") +
                     " | " + ("선택" if alt["selected"] else "미선택") + " | " +
                     " ".join(alt["tradeoffs"]).replace("|", "/") + " |")
    lines += ["", "## 5. 승인 전 조치", ""]
    lines.extend("- [" + finding["rule_id"] + "] " + finding["recommended_action"]
                 for finding in validation["findings"])
    lines += ["", "## 6. 승인 조건", "",
              "- 실제 비용·보안·성능·가용성 검토와 담당자 승인 전에는 운영 적합성을 선언하지 않음.",
              "- AI가 제시한 대안은 사용자의 승인 없이 설계에 자동 반영하지 않음.",
              "- IaC 생성 또는 AWS 배포를 수행하지 않음.",
              "", "> 이 기록은 확정 설계가 아닌 검토용 초안입니다.", ""]
    return "\n".join(lines)
