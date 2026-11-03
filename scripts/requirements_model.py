"""사용자가 직접 제공한 비기밀 요구사항과 설계 옵션을 엄격하게 검증합니다."""
import json
from pathlib import Path

FIELDS = {
    "workload": {"auto", "web", "backend", "mobile"},
    "deployment_preference": {"auto", "static", "serverless", "containers"},
    "environment": {"dev", "staging", "production"},
    "data_classification": {"unknown", "public", "internal", "sensitive"},
    "operations_preference": {"minimize_maintenance", "balanced", "high_availability"},
    "rendering_mode": {"static_export", "ssr", "hybrid"},
    "document_database_strategy": {"keep_existing", "evaluate_migration"},
    "alb_scheme": {"internet_facing", "internal"},
    "egress_strategy": {"undecided", "nat_gateway", "vpc_endpoints_only", "nat_plus_endpoints"},
}
OPTIONAL_NUMBERS = {
    "monthly_budget_usd": (0, 10000000),
    "expected_monthly_requests": (0, 100000000000),
    "availability_target_percent": (0, 100),
    "rto_minutes": (0, 525600),
    "rpo_minutes": (0, 525600),
    "average_rps": (0, 1000000),
    "peak_rps": (0, 10000000),
    "peak_concurrent_connections": (0, 10000000),
    "latency_target_ms": (1, 600000),
    "container_port": (1, 65535),
    "database_port": (1, 65535),
    "max_job_duration_seconds": (1, 604800),
}
OPTIONAL_BOOL = {"requires_authentication", "requires_relational_database", "requires_persistent_storage",
                 "external_outbound_required", "requires_host_control"}
OPTIONAL_STRINGS = {"region"}
KNOWN = set(FIELDS) | set(OPTIONAL_NUMBERS) | OPTIONAL_BOOL | OPTIONAL_STRINGS


def parse_requirements(path, root, budget_override=None, workload_override="auto",
                       return_provenance=False):
    """선택 입력 파일의 경로 이탈과 알 수 없는 필드를 거부합니다."""
    values = {}
    if path:
        candidate = (Path(root).resolve() / path).resolve()
        try:
            candidate.relative_to(Path(root).resolve())
        except ValueError as exc:
            raise ValueError("요구사항 파일은 분석 대상 저장소 내부여야 합니다.") from exc
        if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > 16384:
            raise ValueError("요구사항 파일이 없거나, 심볼릭 링크이거나, 16KB를 초과했습니다.")
        try:
            values = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("요구사항 JSON을 읽을 수 없습니다.") from exc
        if not isinstance(values, dict):
            raise ValueError("요구사항은 JSON 객체여야 합니다.")
    if set(values) - KNOWN:
        raise ValueError("지원하지 않는 요구사항 항목: " + ", ".join(sorted(set(values) - KNOWN)))
    for field, options in FIELDS.items():
        if field in values and (not isinstance(values[field], str) or values[field] not in options):
            raise ValueError(field + "은 허용된 값이어야 합니다: " + ", ".join(sorted(options)))
    for field, (minimum, maximum) in OPTIONAL_NUMBERS.items():
        if field in values:
            val = values[field]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not minimum <= val <= maximum:
                raise ValueError(field + "은 지정된 범위의 숫자여야 합니다.")
    for field in OPTIONAL_BOOL:
        if field in values and not isinstance(values[field], bool):
            raise ValueError(field + "은 true/false 값이어야 합니다.")
    if "region" in values and (
        not isinstance(values["region"], str) or len(values["region"]) > 32 or
        not values["region"].replace("-", "").isalnum()
    ):
        raise ValueError("region은 AWS 리전 코드 형태의 문자열이어야 합니다.")
    # 최초 파일 입력과 기본값을 구분해야 시스템 기본값을 사용자 의사로 오해하지 않습니다.
    explicit = set(values)
    if workload_override != "auto":
        if workload_override not in FIELDS["workload"]:
            raise ValueError("올바르지 않은 workload 값입니다.")
        values["workload"] = workload_override
        explicit.add("workload")
    if budget_override is not None:
        if isinstance(budget_override, bool) or not 0 <= budget_override <= 10000000:
            raise ValueError("월 예산은 0~10,000,000 USD 범위여야 합니다.")
        values["monthly_budget_usd"] = budget_override
        explicit.add("monthly_budget_usd")
    if "average_rps" in values and "peak_rps" in values and values["peak_rps"] < values["average_rps"]:
        raise ValueError("peak_rps는 average_rps 이상이어야 합니다.")
    values.setdefault("workload", "auto")
    values.setdefault("deployment_preference", "auto")
    values.setdefault("data_classification", "unknown")
    values.setdefault("environment", "dev")
    return (values, sorted(explicit)) if return_provenance else values


def review_requirements(values):
    questions = []
    if "expected_monthly_requests" not in values:
        questions.append("월간 요청 수는 어느 정도인가요?")
    if "average_rps" not in values or "peak_rps" not in values:
        questions.append("평균 RPS와 피크 RPS는 각각 어느 정도인가요?")
    if "peak_concurrent_connections" not in values:
        questions.append("피크 동시 연결 수는 어느 정도인가요?")
    if "operations_preference" not in values:
        questions.append("운영 우선순위(최소 관리/균형/고가용성)는 무엇인가요?")
    if "availability_target_percent" not in values:
        questions.append("서비스 목표 가용성(SLA/SLO)은 얼마인가요?")
    if "region" not in values:
        questions.append("서비스 배포 리전과 데이터 보관 지역 제약이 있나요?")
    if "rto_minutes" not in values or "rpo_minutes" not in values:
        questions.append("목표 복구시간(RTO)과 복구시점(RPO)은 각각 얼마인가요?")
    if "monthly_budget_usd" not in values:
        questions.append("월간 인프라 예산 상한은 얼마인가요?")
    if values["data_classification"] == "unknown":
        questions.append("처리 데이터의 민감도(공개·내부·민감)는 무엇인가요?")
    return questions
