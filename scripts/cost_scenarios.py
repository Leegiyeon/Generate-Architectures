"""AWS 비용 v2: 사용자 제공 최소/기준/피크 수량과 정적 토폴로지 비용 항목 대응.

단가·RPS·컴퓨팅 규모를 자동 추측하지 않습니다. AWS Price List 단가 조회는
사용자가 --live-pricing을 명시했을 때만 기존 cost_estimator 경로를 사용합니다.
"""
from decimal import Decimal

SCENARIOS = ("minimum", "baseline", "peak")
SERVICES = {
    "alb", "ecs_fargate", "rds", "ec2", "cloudfront", "s3",
    "api_gateway", "lambda", "dynamodb", "cognito", "nat_gateway",
    "vpc_endpoints", "data_transfer", "cloudwatch_logs", "backup_storage",
    "other",
}


def validate_scenario_config(doc):
    """v2 입력을 세 개의 v1 정규화 구조로 검증하여 동일 단가/리전 정책 유지."""
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "region", "items"}:
        raise ValueError("비용 v2는 schema_version, region, items만 허용합니다.")
    if doc["schema_version"] != "2.0":
        raise ValueError("지원하는 비용 시나리오 형식은 2.0입니다.")
    if not isinstance(doc["items"], list) or len(doc["items"]) > 30:
        raise ValueError("비용 입력 항목은 30개 이하여야 합니다.")
    normalized = {s: [] for s in SCENARIOS}
    for item in doc["items"]:
        if not isinstance(item, dict) or set(item) != {
            "id", "service", "unit", "quantities", "rate"
        }:
            raise ValueError("v2 항목에는 id/service/unit/quantities/rate가 필요합니다.")
        if not isinstance(item["service"], str) or item["service"] not in SERVICES:
            raise ValueError("지원하지 않는 비용 서비스 분류입니다.")
        q = item["quantities"]
        if not isinstance(q, dict) or set(q) != set(SCENARIOS):
            raise ValueError("각 서비스의 minimum/baseline/peak 사용량을 모두 입력해야 합니다.")
        try:
            amounts = [Decimal(str(q[s])) for s in SCENARIOS]
        except (ValueError, ArithmeticError):
            raise ValueError("비용 시나리오 사용량은 유한한 숫자여야 합니다.") from None
        if any(isinstance(q[s], bool) or not isinstance(q[s], (int, float)) or
               not amount.is_finite() or amount < 0 or amount > Decimal("1e12")
               for s, amount in zip(SCENARIOS, amounts)):
            raise ValueError("비용 시나리오 사용량은 0 이상 유한한 숫자여야 합니다.")
        if amounts != sorted(amounts):
            raise ValueError("사용량은 minimum <= baseline <= peak를 만족해야 합니다.")
        for s in SCENARIOS:
            normalized[s].append({
                "id": item["id"], "quantity": q[s], "unit": item["unit"],
                "rate": item["rate"],
            })
    # 기존 가격 입력의 공식 출처/리전·항목 고유성/SKU 검증을 그대로 재사용합니다.
    try:
        from .cost_estimator import validate_legacy_cost_doc
    except ImportError:
        from cost_estimator import validate_legacy_cost_doc
    for s in SCENARIOS:
        validate_legacy_cost_doc({"region": doc["region"], "items": normalized[s]})
    return doc


def estimate_scenarios(config, *, live=False, client=None):
    """동일한 단가는 한 번만 확인하고 사용자 수량 3세트에 재사용."""
    try:
        from .cost_estimator import estimate_costs
    except ImportError:
        from cost_estimator import estimate_costs
    unit_config = {
        "region": config["region"],
        "items": [
            {"id": x["id"], "quantity": 1, "unit": x["unit"], "rate": x["rate"]}
            for x in config["items"]
        ],
    }
    resolved = estimate_costs(unit_config, live=live, client=client)
    scenarios={}
    for key in SCENARIOS:
        lines=[]
        subtotal=Decimal(0)
        for item, price in zip(config["items"], resolved["lines"]):
            unit_price = price["unit_price_usd"]
            amount = (Decimal(str(item["quantities"][key])) * Decimal(unit_price)
                      if unit_price is not None else None)
            if amount is not None:
                subtotal += amount
            line = dict(price)
            line.update({
                "service": item["service"],
                "quantity": str(item["quantities"][key]),
                "monthly_amount_usd": str(amount) if amount is not None else None,
                "status": "estimated" if amount is not None else "unpriced",
            })
            lines.append(line)
        unknown=sum(line["status"]=="unpriced" for line in lines)
        complete=bool(lines) and unknown==0
        scenarios[key]={
            "status": "scenario_estimate" if complete else "partial_unpriced",
            "complete_for_provided_items": complete,
            "monthly_total_usd": str(subtotal) if complete else None,
            "priced_subtotal_usd": str(subtotal) if any(x["status"] == "estimated" for x in lines) else None,
            "unpriced_count": unknown,
            "lines": lines,
        }
    baseline=scenarios["baseline"]
    # legacy report_bundle/validation callers get the baseline fields unchanged.
    return {
        "schema_version": "2.0",
        "status": baseline["status"] if config["items"] else "needs_input",
        "complete": baseline["complete_for_provided_items"],
        "currency": "USD",
        "region": config["region"],
        "monthly_total_usd": baseline["monthly_total_usd"],
        "priced_subtotal_usd": baseline["priced_subtotal_usd"],
        "lines": baseline["lines"],
        "unpriced_count": baseline["unpriced_count"],
        "scenarios": scenarios,
        "quantities_source": "user_provided_per_scenario",
        "service_coverage_status": "not_checked",
        "note": ("최소/기준/피크는 사용자가 직접 제공한 월 사용량입니다. "
                 "피크 RPS에서 사용량을 자동 산출하지 않았으며, 입력 항목만 계산합니다. "
                 "실제 총 청구액/예약형 할인·세금·트래픽/백업 전체 비용은 별도 확인이 필요합니다."),
    }


def correlate_topology_costs(report, topology, requirements):
    """AWS To-Be 구조별 필수 비용 분류가 모두 입력됐는지 보수적으로 표시."""
    nodes = {n["id"] for n in topology["nodes"]}
    expected=set()
    if "alb" in nodes:
        expected.add("alb")
    if any(x.startswith("task_") for x in nodes):
        expected.add("ecs_fargate")
    if "rds" in nodes:
        expected |= {"rds", "backup_storage"}
    if any(x.startswith("nat_") for x in nodes):
        expected.add("nat_gateway")
    if any(x.startswith("vpce_") for x in nodes):
        expected.add("vpc_endpoints")
    if "api" in nodes:
        expected.add("api_gateway")
    if "lambda" in nodes:
        expected.add("lambda")
    if "dynamodb" in nodes:
        expected.add("dynamodb")
    if "cognito" in nodes:
        expected.add("cognito")
    if "cdn" in nodes:
        expected.add("cloudfront")
    if "bucket" in nodes:
        expected.add("s3")
    if "observability" in nodes:
        expected.add("cloudwatch_logs")
    if "client" in nodes:
        expected.add("data_transfer")
    selected={x.get("service") for x in report["lines"] if x.get("service")}
    missing=sorted(expected - selected)
    region=topology.get("region")
    region_match=region is None or region==report.get("region")
    report["topology_coverage"]={
        "status": ("legacy_items_not_mapped" if "scenarios" not in report
                   else "region_mismatch" if not region_match
                   else "missing_cost_categories" if missing
                   else "cost_categories_tagged_not_sku_verified"),
        "required_service_categories":sorted(expected),
        "provided_categories":sorted(selected),
        "missing_categories":missing,
        "region_matched":region_match,
        "region_confirmed":bool(region),
        "full_aws_bill_estimated":False,
        "note": ("분류별 항목 존재 여부만 대조합니다. 실제 SKU, 요청/사용량 모델, "
                 "서비스별 추가 요금과 비용 완전성을 증명하지 않습니다."),
    }
    report["complete_for_entire_architecture"]=False
    report["pricing_applicable_to_selected_region"]=region_match
    return report


def scenario_markdown(report):
    """비교가 가능한 구간은 입력된 서비스 항목별 비용으로만 제한."""
    if "scenarios" not in report:
        return ""
    rows=["## 최소 / 기준 / 피크 사용자 입력 시나리오", "",
          "> 피크 RPS와 시나리오별 월 사용량을 같은 값으로 간주하지 않습니다.",
          "", "| 시나리오 | 계산된 부분합 USD | 입력 항목 전부 계산된 경우 합계 USD | 단가 누락 항목 |",
          "| --- | ---: | ---: | ---: |"]
    for key,title in (("minimum","최소"),("baseline","기준"),("peak","피크")):
        s=report["scenarios"][key]
        rows.append("| "+title+" | "+(s["priced_subtotal_usd"] or "미산정")+" | "+
                    (s["monthly_total_usd"] if s["monthly_total_usd"] is not None
                     else "미산정") + " | "+str(s["unpriced_count"])+" |")
    c=report.get("topology_coverage", {})
    rows+=["", "## AWS To-Be 구성요소 대비 비용 분류 확인", "",
           "- 커버리지: "+c.get("status","미검증"),
           "- 누락한 비용 분류: "+(", ".join(c.get("missing_categories", []))
                            if c.get("missing_categories") else "분류상 없음 (SKU 검증 전)"),
           "- 리전 일치: "+str(c.get("region_matched")),
           "- **전체 아키텍처 비용 완결 판정은 제공하지 않습니다.**",
           "- 증가 요인: 서비스 사용량 증가, 오토스케일 태스크 수, NAT/데이터 전송량, DB/로그/백업·관측 비용.",
           "- 사용량 민감도는 각 후보별 기입한 수량의 차이에 한정하며 실제 부하/서비스 쿼터를 검증하지 않았습니다.",
           ""]
    return "\n".join(rows)
