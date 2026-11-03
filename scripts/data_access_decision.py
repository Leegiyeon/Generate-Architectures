"""저장소 DB 신호와 명시적인 데이터 요구를 분리한 AWS 저장소 대안 검토.

이 모듈은 실제 DB 엔진/스키마/워크로드를 조회하지 않으며, 자동 마이그레이션을
선정하지 않습니다. 사용자가 단정한 전환 목표라도 별도 검증·승인 필요입니다.
"""
PATTERNS = {
    "relational_transactions": "관계형 트랜잭션/조인",
    "document_queries": "문서·중첩 문서 조회",
    "key_value": "키 기반 단건 조회",
    "undecided": "아직 데이터 접근 패턴 미확정",
}
OPTIONS = {
    "rds": {
        "title": "Amazon RDS (PostgreSQL/MySQL 등)",
        "strengths": ["관계형 제약·트랜잭션·SQL 쿼리 유지 검토"],
        "conditions": ["DB 엔진/버전·연결 수·Multi-AZ/백업·암호화·비용 확인"],
    },
    "dynamodb": {
        "title": "Amazon DynamoDB",
        "strengths": ["키 기반 접근 패턴과 관리형 저장소 검토"],
        "conditions": ["Access Pattern/파티션 키·용량/비용·트랜잭션/쿼리 제약 검증"],
    },
    "existing_document": {
        "title": "기존 MongoDB 또는 문서형 DB 유지",
        "strengths": ["기존 컬렉션·쿼리·드라이버 호환성 보존 검토"],
        "conditions": ["기존 DB 제공자/네트워크/TLS/백업·운영 책임 확인"],
    },
    "documentdb": {
        "title": "Amazon DocumentDB (별도 호환성 검증)",
        "strengths": ["AWS 관리형 문서형 DB 후보"],
        "conditions": ["MongoDB와 완전 동일 제품이 아님. API/버전/쿼리/인덱스·마이그레이션 검증 필요"],
    },
}


def assess_data_access(profile, requirements, contract):
    explicit = {x["key"]: x["id"] for x in contract["user_requirements"]}
    inferred = {x["signal"]: x["id"] for x in contract["configuration_inferences"]}
    signals = profile.get("signals", {})
    rel = signals.get("relational_database") is True
    doc = signals.get("document_database") is True
    pattern = requirements.get("data_access_pattern", "undecided")
    migration = requirements.get("database_migration_approved") is True
    strategy = requirements.get("document_database_strategy", "undecided")
    required_rel = requirements.get("requires_relational_database")
    required_storage = requirements.get("requires_persistent_storage")
    if pattern not in PATTERNS:
        raise ValueError("알 수 없는 데이터 액세스 유형입니다.")
    notes = []
    def note(code, detail, keys=()):
        notes.append({
            "rule_id": code, "detail": detail, "status": "review_required",
            "evidence_ids": [explicit[k] for k in keys if k in explicit],
        })
    if pattern == "undecided":
        note("DATA-PATTERN", "데이터 읽기/쓰기·조인·조회 빈도·일관성 수준이 명시되지 않았습니다.")
    if required_storage is False and (rel or doc or required_rel is True):
        note("DATA-STORAGE-CONFLICT", "영속 저장 불필요 입력과 DB 의존성/관계형 DB 필요 조건을 재확인하세요.",
             ("requires_persistent_storage", "requires_relational_database"))
    if rel and pattern == "key_value":
        note("DATA-RELATIONAL-KEY", "관계형 DB 라이브러리 단서가 있지만 키-값 액세스 요구가 있습니다. 기존 쿼리/조인이 남는지 확인하세요.",
             ("data_access_pattern",))
    if doc and pattern == "relational_transactions":
        note("DATA-DOCUMENT-SQL", "문서형 DB 단서와 관계형 트랜잭션 요구가 상충할 수 있으므로 기존 쿼리를 검증하세요.",
             ("data_access_pattern",))
    if doc and not migration:
        note("DATA-DOCUMENT-KEEP", "문서형 DB를 DynamoDB/DocumentDB로 자동 전환할 근거 또는 승인 없음.")
    candidates=[]
    for ident, definition in OPTIONS.items():
        blockers=[]
        cautions=list(definition["conditions"])
        if ident == "rds":
            if doc and required_rel is not True and not migration:
                blockers.append("문서형 DB만 탐지되었고 RDS 전환 승인 및 관계형 DB 요구가 없습니다.")
            if pattern == "document_queries" and required_rel is not True:
                cautions.append("문서형 조회를 SQL로 재설계하려면 스키마와 쿼리 호환성 검증 필요.")
        elif ident == "dynamodb":
            if (rel or doc or required_rel is True) and not migration:
                blockers.append("기존 DB/관계형 요구의 DynamoDB 전환에 대한 명시적 승인 없음.")
            if pattern == "relational_transactions":
                cautions.append("조인/참조무결성 등 관계형 모델의 재설계가 필요할 수 있습니다.")
        elif ident == "existing_document":
            if not doc and pattern != "document_queries":
                cautions.append("문서형 DB 필요성이 코드나 사용자 입력에서 확인되지 않았습니다.")
        elif ident == "documentdb":
            if (rel or doc) and not migration:
                blockers.append("기존 DB의 DocumentDB 전환 승인 없음.")
            if strategy == "keep_existing" and doc:
                blockers.append("기존 문서형 DB 유지 요구와 DocumentDB로 교체하는 선택이 충돌합니다.")
        candidates.append({
            "id": ident, "name": definition["title"],
            "status": "blocked_for_migration" if blockers else "review_required",
            "blockers": blockers, "strengths": definition["strengths"],
            "review_required": cautions, "approved": False,
            "source_ids": [explicit[k] for k in
                ("data_access_pattern", "requires_relational_database",
                 "database_migration_approved", "document_database_strategy") if k in explicit]
                + [inferred[k] for k in ("relational_database", "document_database") if k in inferred],
        })
    return {
        "schema_version": "1.0", "status": "proposed_unverified",
        "data_access_pattern": pattern,
        "pattern_source": "explicit_user_input" if "data_access_pattern" in explicit else "not_provided",
        "observed_relational_indicator": rel,
        "observed_document_indicator": doc,
        "migration_approved_for_automatic_change": False,
        "migration_review_requested": migration,
        "candidates": candidates, "review_required": notes,
        "selected_data_store": None,
        "limitations": [
            "단순 의존성 탐지만으로 실제 DB 사용, 스키마/쿼리, 프로덕션 데이터의 존재를 확정할 수 없습니다.",
            "마이그레이션 승인 플래그는 검토 의사이며 제품이 실제 DB/스키마를 변경할 권한은 없습니다.",
            "AWS 서비스 데이터 계층 선정은 사용자가 구조·쿼리·비용·정합성을 검증한 뒤 승인해야 합니다.",
        ],
    }


def markdown_data_access(report):
    lines = [
        "# 데이터 접근 패턴 및 AWS 저장소 대안", "",
        "> 스키마/실제 조회/DB 엔진은 실행·검증하지 않았으며 실제 데이터 변경이 없습니다.",
        "", "- 데이터 접근 패턴: " + PATTERNS[report["data_access_pattern"]],
        "- 입력 출처: " + report["pattern_source"],
        "- 관계형 DB 단서: " + str(report["observed_relational_indicator"]),
        "- 문서형 DB 단서: " + str(report["observed_document_indicator"]),
        "- DB 자동 마이그레이션: 사용 안 함", "",
        "| 후보 | 상태 | 제약/확인 필요 |", "| --- | --- | --- |",
    ]
    for option in report["candidates"]:
        reasons = option["blockers"] or option["review_required"]
        lines.append("| " + option["name"] + " | " + option["status"] +
                     " | " + " / ".join(reasons).replace("|", "/") + " |")
    lines += ["", "## 확인할 요구사항", ""]
    lines.extend("- [" + x["rule_id"] + "] " + x["detail"]
                 for x in report["review_required"])
    lines += ["", "## 제한 사항", ""]
    lines.extend("- " + x for x in report["limitations"])
    return "\n".join(lines) + "\n"
