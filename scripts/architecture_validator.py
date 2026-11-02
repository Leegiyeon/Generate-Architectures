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
