"""동일 사용자 업무량을 대상으로 ECS Fargate/EC2/Lambda 대안의 입력 비용만 비교.

가격은 기존 엄격한 v2 시나리오/Price List 파서가 계산합니다.
요금·인스턴스 수·성능/RPS→용량 환산·실제 배포는 이 모듈에서 추측하거나 실행하지 않습니다.
후보별 서비스 및 운영 책임을 구분하고 비용/성능 적합성을 자동 승인하지 않습니다.
"""
from decimal import Decimal
import json
from pathlib import Path
import re

try:
    from .cost_scenarios import SCENARIOS, validate_scenario_config
    from .cost_estimator import estimate_costs
except ImportError:
    from cost_scenarios import SCENARIOS, validate_scenario_config
    from cost_estimator import estimate_costs

MAX_FILE_BYTES = 65536
ID = re.compile(r"[a-zA-Z0-9._-]{1,48}\Z")
PATTERNS = ("fargate", "ec2", "lambda")
REQUIRED_COST_CATEGORIES = {
    "fargate": ("alb", "ecs_fargate", "data_transfer", "cloudwatch_logs"),
    "ec2": ("alb", "ec2", "data_transfer", "cloudwatch_logs"),
    "lambda": ("api_gateway", "lambda", "data_transfer", "cloudwatch_logs"),
}
OPERATIONS = {
    "fargate": {
        "platform": "컨테이너 이미지·작업 정의·서비스 정책/헬스체크·ECS Auto Scaling",
        "security": "Task/Execution IAM Role·Private Egress·ALB→ECS SG·Secrets",
        "maintenance": "컨테이너/런타임 패치·이미지 취약점·배포 롤백, OS 패치는 AWS 책임",
        "verification": "vCPU·메모리·추가 스토리지/ALB LCU·NAT·Task 수, AZ별 배치 실측",
    },
    "ec2": {
        "platform": "인스턴스 유형·AMI·Launch Template·Auto Scaling/Target Group",
        "security": "EC2 인스턴스 프로파일·SSH/SSM·OS/SG·EBS 암호화·Private Egress",
        "maintenance": "OS·AMI·패치·EBS 백업·CloudWatch Agent·롤백 운영 책임",
        "verification": "실제 EC2 인스턴스/스토리지/EBS IOPS·라이선스·ALB LCU·용량 검증",
    },
    "lambda": {
        "platform": "API Gateway·Lambda 동시성/함수 실행시간·타임아웃/요청 제한",
        "security": "함수 실행 Role·API Authorizer·Secrets·VPC 연결/외부 API 제약",
        "maintenance": "함수 런타임·의존 라이브러리/배포 관리; OS 관리 불필요",
        "verification": "요청 수·실행 GB-Seconds/메모리, API Gateway 요금·동시성/쿼터/콜드스타트 시험",
    },
}
REFERENCES = {
    "fargate": "https://aws.amazon.com/fargate/pricing/",
    "ec2": "https://aws.amazon.com/ec2/pricing/on-demand/",
    "lambda": "https://aws.amazon.com/lambda/pricing/",
    "api": "https://aws.amazon.com/api-gateway/pricing/",
}


def _numeric(value, maximum=1000000000000):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and
            Decimal(str(value)).is_finite() and Decimal(0) <= Decimal(str(value)) <= maximum)


def read_alternative_cost_input(root, path):
    """분석 저장소 내부 일반 JSON만 허용; 경로이탈·시크릿 파일·심볼릭 링크 금지."""
    if not path:
        return None
    base = Path(root).resolve()
    candidate = base / path
    if candidate.is_symlink():
        raise ValueError("대안 비용 입력은 심볼릭 링크를 사용할 수 없습니다.")
    selected = candidate.resolve()
    if not selected.is_relative_to(base) or not selected.is_file():
        raise ValueError("대안 비용 입력은 분석 저장소 내부 JSON 파일이어야 합니다.")
    if selected.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("대안 비용 입력은 64KB를 초과할 수 없습니다.")
    try:
        data = json.loads(selected.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise ValueError("대안 비용 JSON을 읽을 수 없습니다.") from exc
    return validate_alternative_cost_input(data)


def validate_alternative_cost_input(data):
    """업무량/리전이 모든 후보에서 공통이라는 계약을 스키마 수준에서 강제."""
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "region", "workload", "shared_items", "candidates"
    } or data["schema_version"] != "1.0":
        raise ValueError("비교 입력은 schema_version/region/workload/shared_items/candidates 구조여야 합니다.")
    workload = data["workload"]
    if not isinstance(workload, dict) or set(workload) != {
        "id", "monthly_requests", "peak_rps"
    } or not isinstance(workload["id"], str) or not ID.fullmatch(workload["id"]):
        raise ValueError("비교 대상 workload는 식별자·월 요청 수·피크 RPS가 필요합니다.")
    counts = workload["monthly_requests"]
    if not isinstance(counts, dict) or set(counts) != set(SCENARIOS):
        raise ValueError("동일 업무의 최소/기준/피크 월 요청 수를 모두 입력해야 합니다.")
    values = [counts[s] for s in SCENARIOS]
    if any(not _numeric(q) for q in values) or [
        Decimal(str(q)) for q in values
    ] != sorted(Decimal(str(q)) for q in values):
        raise ValueError("월 요청 수는 0 이상이며 최소≤기준≤피크를 따라야 합니다.")
    if not _numeric(workload["peak_rps"], 10000000):
        raise ValueError("피크 RPS는 0 이상 유한한 사용자 수치여야 합니다.")
    shared = data["shared_items"]
    candidates = data["candidates"]
    if not isinstance(shared, list) or len(shared) > 20 or (
        not isinstance(candidates, list) or not 2 <= len(candidates) <= 3
    ):
        raise ValueError("공통 비용 항목 최대 20개, 대안 후보 2~3개가 필요합니다.")
    ids = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {"id", "items"}:
            raise ValueError("각 후보에는 id와 items만 입력하세요.")
        name = candidate["id"]
        if not isinstance(name, str) or name not in PATTERNS or name in ids:
            raise ValueError("후보 id는 서로 다른 fargate/ec2/lambda여야 합니다.")
        ids.add(name)
        if not isinstance(candidate["items"], list):
            raise ValueError("후보 비용 항목은 리스트여야 합니다.")
        # 기존 v2 검증을 재사용해 AWS 단가 출처/숫자·리전·중복 ID·단위를 검사합니다.
        validate_scenario_config({
            "schema_version": "2.0", "region": data["region"],
            "items": shared + candidate["items"],
        })
        specific = {i["service"] for i in candidate["items"]}
        if not specific.intersection(set(REQUIRED_COST_CATEGORIES[name])):
            raise ValueError("후보의 실행 서비스 비용 항목이 누락됐습니다.")
    return data


def compare_alternatives(data, requirements, decision_matrix, *, live=False, client=None):
    """사용자가 제공한 동일 업무/월 사용량에서 항목 한정 비용과 운영 책임 비교."""
    if data is None:
        return {
            "schema_version": "1.0", "status": "needs_input",
            "workload": None, "candidates": [], "comparisons": [],
            "region_matched": None, "requirements_matched": None,
            "recommended_by_cost": None, "auto_selected": False,
            "production_ready": False, "capacity_benchmarked": False,
            "note": "대안별 공통 업무량·서비스별 사용량과 단가 입력이 없어 비용 비교하지 않았습니다.",
        }
    validate_alternative_cost_input(data)
    explicit_checks = {}
    for requirement_key, supplied in (
        ("expected_monthly_requests", data["workload"]["monthly_requests"]["baseline"]),
        ("peak_rps", data["workload"]["peak_rps"]),
    ):
        if requirement_key in requirements:
            explicit_checks[requirement_key] = Decimal(str(requirements[requirement_key])) == Decimal(str(supplied))
    if "region" in requirements:
        explicit_checks["region"] = data["region"] == requirements["region"]
    requirements_matched = all(explicit_checks.values())
    decision_by_id = {c["id"]: c for c in decision_matrix["candidates"]}
    items = []
    all_complete = True
    all_required = True
    any_blockers = False
    for candidate in sorted(data["candidates"], key=lambda c: PATTERNS.index(c["id"])):
        name = candidate["id"]
        if name not in decision_by_id:
            raise ValueError("AWS 실행 패턴 매트릭스에 없는 후보입니다.")
        document = {
            "schema_version": "2.0", "region": data["region"],
            "items": data["shared_items"] + candidate["items"],
        }
        estimate = estimate_costs(document, live=live, client=client)
        selected_services = {i["service"] for i in document["items"]}
        missing = sorted(set(REQUIRED_COST_CATEGORIES[name]) - selected_services)
        blocked = decision_by_id[name]["blockers"]
        any_blockers = any_blockers or bool(blocked)
        complete = all(estimate["scenarios"][s]["complete_for_provided_items"] for s in SCENARIOS)
        all_complete = all_complete and complete
        all_required = all_required and not missing
        # 전체 AWS 비용이 아니라 사용자가 가격/수량을 명시한 항목에 한정합니다.
        items.append({
            "id": name, "status": "blocked_for_current_template" if blocked else
                  "input_costs_complete" if complete and not missing else
                  "incomplete_cost_model",
            "required_categories": list(REQUIRED_COST_CATEGORIES[name]),
            "missing_categories": missing,
            "price_scope_complete": complete,
            "price_status": estimate["status"],
            "blockers": list(blocked),
            "operational_responsibilities": OPERATIONS[name],
            "scenarios": {s: {
                "priced_subtotal_usd": estimate["scenarios"][s]["priced_subtotal_usd"],
                "provided_items_total_usd": estimate["scenarios"][s]["monthly_total_usd"],
                "unpriced_items": estimate["scenarios"][s]["unpriced_count"],
                "priced_item_count": sum(x["status"] == "estimated"
                                         for x in estimate["scenarios"][s]["lines"]),
            } for s in SCENARIOS},
            "pricing_sources": [{
                "id": x["id"], "service": x["service"], "rate_source": x["rate_source"],
                "sku": x.get("sku"), "price_effective_date": x.get("price_effective_date"),
                "source_reference": x["source_reference"], "price_model": x.get("price_model"),
            } for x in estimate["lines"]],
            "monthly_requests": dict(data["workload"]["monthly_requests"]),
            "capacity_benchmarked": False,
            "full_aws_bill_estimated": False, "approved": False,
        })
    ready_for_input_comparison = (
        requirements_matched and all_complete and all_required and not any_blockers
    )
    comparisons = []
    if ready_for_input_comparison:
        # 차액은 오직 사용자 입력 비용 항목끼리의 산술 비교이며 서비스 우열이 아닙니다.
        for scenario in SCENARIOS:
            amounts = {c["id"]: Decimal(c["scenarios"][scenario]["provided_items_total_usd"])
                       for c in items}
            minimum = min(amounts.values())
            comparisons.append({
                "scenario": scenario, "least_modeled_amount_usd": str(minimum),
                "modeled_costs_usd": {k: str(v) for k, v in amounts.items()},
                "deltas_from_minimum_modeled_usd":
                    {k: str(v - minimum) for k, v in amounts.items()},
                "only_input_items": True, "validated_real_workload": False,
            })
    return {
        "schema_version": "1.0",
        "status": "modeled_items_comparable_unverified" if ready_for_input_comparison
                  else "blocked_by_constraints" if any_blockers
                  else "requirements_mismatch" if not requirements_matched
                  else "missing_service_cost_categories" if not all_required
                  else "partial_unpriced",
        "workload": dict(data["workload"]),
        "region": data["region"], "region_matched": explicit_checks.get("region"),
        "requirements_checks": explicit_checks,
        "requirements_matched": requirements_matched,
        "candidates": items, "comparisons": comparisons,
        "recommended_by_cost": None, "auto_selected": False,
        "architecture_selection_unchanged": True,
        "production_ready": False, "capacity_benchmarked": False,
        "pricing_live_requested": bool(live),
        "references": REFERENCES,
        "note": ("동일 사용자 입력 업무량을 비교한 것일 뿐 ECS/EC2/Lambda의 처리량·SLO·"
                 "기능 동등성을 검증하지 않았습니다. 비용이 모두 산출되어도 AWS 전체 청구액·"
                 "실제 비용 최저가/운영 적합성/배포 승인 근거가 아닙니다."),
    }


def markdown_comparison(report):
    lines = [
        "# 동일 업무량 AWS 실행 방식별 비용·유지보수 비교", "",
        "> **사용자 입력 비용 항목만 검토**. 실제 AWS 청구액/처리량/최적 서비스 추천이 아닙니다.",
        "", "- 상태: " + report["status"], "- AWS 자원 변경: 없음",
        "- 비용 기반 자동 선정: 없음", "- 실제 용량/부하 검증: 미실시", "",
    ]
    if report["workload"] is None:
        lines += ["## 입력 대기", "",
                  "대안 비용 입력 JSON을 지정해야 ECS Fargate/EC2/Lambda의 비용 항목을 비교할 수 있습니다.",
                  "사용 방법: docs/ALTERNATIVE_COST_COMPARISON.md", ""]
        return "\n".join(lines)
    workload = report["workload"]
    lines += ["- 공통 월 업무량 ID: " + workload["id"],
              "- 최소/기준/피크 월 요청: " +
                " / ".join(str(workload["monthly_requests"][s]) for s in SCENARIOS),
              "- 사용자 입력 피크 RPS: " + str(workload["peak_rps"]),
              "- 기존 요구사항과의 일치: " + str(report["requirements_matched"]), "",
              "## 후보별 월 모델 비용", "",
              "| 실행 패턴 | 최소 USD | 기준 USD | 피크 USD | 누락 서비스 분류 | 제약 상태 |",
              "| --- | ---: | ---: | ---: | --- | --- |"]
    for row in report["candidates"]:
        amounts = [row["scenarios"][s]["provided_items_total_usd"] or
                   ("부분합: " + row["scenarios"][s]["priced_subtotal_usd"]
                    if row["scenarios"][s]["priced_subtotal_usd"] is not None
                    else "미산정") for s in SCENARIOS]
        lines.append("| " + row["id"] + " | " + " | ".join(amounts) + " | " +
                     (", ".join(row["missing_categories"]) or "분류 기준 없음") +
                     " | " + row["status"] + " |")
    lines += ["", "## 운영·보안·유지보수 책임", ""]
    for row in report["candidates"]:
        lines += ["### " + row["id"], "",
                  "- 운영: " + row["operational_responsibilities"]["platform"],
                  "- 보안: " + row["operational_responsibilities"]["security"],
                  "- 유지보수: " + row["operational_responsibilities"]["maintenance"],
                  "- 실제 검증: " + row["operational_responsibilities"]["verification"]]
        lines += ["- 차단: [" + x["rule_id"] + "] " + x["reason"]
                  for x in row["blockers"]]
    lines += ["", "## 입력 금액 차이(제한된 산술 비교)", ""]
    if not report["comparisons"]:
        lines.append("- 실제 요구/서비스 비용 분류/가격/현재 템플릿의 제약이 해결되지 않아 금액 차액을 산출하지 않습니다.")
    for compare in report["comparisons"]:
        lines += ["- " + compare["scenario"] + ": " +
                  ", ".join(k + " +" + str(v) + " USD" for k, v in
                            compare["deltas_from_minimum_modeled_usd"].items()) +
                  " (입력 항목만, AWS 전체 차이 아님)"]
    lines += ["", "## 필수 후속 검증", "",
              "- 동일 API 응답/데이터베이스/보안·가용성 요구를 충족하는지 실제 실행 시험",
              "- 인스턴스·태스크·동시 실행 수/저장/데이터 전송·CloudWatch·요청의 리전별 SKU 단가 검증",
              "- 최소·기준·피크 부하 테스트 및 장애/복원·OS 패치·런북 책임 검토",
              "- 실제 계정의 무료 티어/약정/크레딧/세금 반영은 별도",
              "", report["note"], ""]
    return "\n".join(lines)
