"""보수적인 AWS 비용 시나리오 계산: 근거 없는 단가와 총액을 생성하지 않습니다.

기본 모드: 입력된 사용량과 단가의 출처를 검증. 명시적 동의 시에만
AWS Price List Query API(boto3, pricing:GetProducts)에서 지정 SKU 조회.
실제 청구액/세금/할인/무료 한도 및 계정 사용량을 반영하지 않습니다.
"""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.parse import urlsplit
from datetime import date
import re

MAX_FILE_BYTES = 32768
ALLOWED_UNITS = {"Requests", "Hrs", "GB-Mo", "GB", "GB-Seconds", "vCPU-Hours",
                 "GB-Hours", "Count", "1M Requests"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,48}$")
REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_cost_inputs(root, path):
    if not path:
        return None
    target = (Path(root).resolve() / path).resolve()
    if not target.is_relative_to(Path(root).resolve()) or target.is_symlink():
        raise ValueError("비용 입력은 저장소 내부의 일반 파일이어야 합니다.")
    if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("비용 입력 파일이 없거나 32KB를 초과했습니다.")
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("비용 입력 JSON을 읽을 수 없습니다.") from exc
    # 기존 단일 시나리오와 v2(최소/기준/피크) 입력 모두 안전하게 지원합니다.
    if isinstance(doc, dict) and doc.get("schema_version") == "2.0":
        try:
            from .cost_scenarios import validate_scenario_config
        except ImportError:
            from cost_scenarios import validate_scenario_config
        return validate_scenario_config(doc)
    return validate_legacy_cost_doc(doc)


def validate_legacy_cost_doc(doc):
    """입력 파일과 시나리오 재사용에 공통으로 적용할 단가 출처·리전·수량 검증."""
    if not isinstance(doc, dict) or set(doc) != {"region", "items"} or not REGION.fullmatch(str(doc["region"])):
        raise ValueError("region 및 items만 포함하는 비용 JSON이 필요합니다.")
    if not isinstance(doc["items"], list) or len(doc["items"]) > 30:
        raise ValueError("비용 항목은 최대 30개여야 합니다.")
    seen = set()
    for item in doc["items"]:
        if not isinstance(item, dict) or set(item) != {"id", "quantity", "unit", "rate"}:
            raise ValueError("비용 항목은 id, quantity, unit, rate를 포함해야 합니다.")
        if not isinstance(item["id"], str) or not IDENTIFIER.fullmatch(item["id"]) or item["id"] in seen:
            raise ValueError("비용 항목 ID가 올바르지 않거나 중복되었습니다.")
        seen.add(item["id"])
        if not isinstance(item["unit"], str) or item["unit"] not in ALLOWED_UNITS:
            raise ValueError("지원되지 않는 사용량 단위입니다.")
        try:
            q = Decimal(str(item["quantity"]))
        except (InvalidOperation, ValueError):
            raise ValueError("사용량은 숫자여야 합니다.") from None
        if isinstance(item["quantity"], bool) or not q.is_finite() or q < 0 or q > Decimal("1e12"):
            raise ValueError("사용량은 0 이상 유한한 숫자여야 합니다.")
        rate = item["rate"]
        if not isinstance(rate, dict) or rate.get("kind") not in ("manual_quote", "aws_price_list", "unknown"):
            raise ValueError("단가 근거 유형이 올바르지 않습니다.")
        if rate["kind"] == "unknown" and set(rate) != {"kind"}:
            raise ValueError("미확인 단가는 kind만 포함해야 합니다.")
        if rate["kind"] == "manual_quote":
            if set(rate) != {"kind", "unit_price_usd", "source", "as_of"} or not DATE.fullmatch(str(rate["as_of"])):
                raise ValueError("수동 단가는 금액, 출처, 기준일이 필수입니다.")
            if not isinstance(rate["source"], str) or not 8 <= len(rate["source"]) <= 150:
                raise ValueError("단가 출처를 명시해야 합니다.")
            parsed = urlsplit(rate["source"])
            if parsed.scheme != "https" or parsed.hostname not in {
                "aws.amazon.com", "calculator.aws", "docs.aws.amazon.com",
            } or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("수동 단가 출처는 공식 AWS 가격 링크(쿼리/자격증명 제외)여야 합니다.")
            try:
                date.fromisoformat(rate["as_of"])
            except ValueError:
                raise ValueError("단가 기준일이 유효하지 않습니다.") from None
            try:
                cost = Decimal(str(rate["unit_price_usd"]))
            except (InvalidOperation, ValueError):
                raise ValueError("단가 값이 유효하지 않습니다.") from None
            if isinstance(rate["unit_price_usd"], bool) or not cost.is_finite() or cost < 0 or cost > Decimal("1e9"):
                raise ValueError("단가 범위가 올바르지 않습니다.")
        if rate["kind"] == "aws_price_list":
            if set(rate) != {"kind", "service_code", "filters"}:
                raise ValueError("Price List 조회에는 service_code 및 filters가 필요합니다.")
            if not isinstance(rate["service_code"], str) or not IDENTIFIER.fullmatch(rate["service_code"]):
                raise ValueError("잘못된 AWS 서비스 코드입니다.")
            if not isinstance(rate["filters"], dict) or not 1 <= len(rate["filters"]) <= 8:
                raise ValueError("AWS 상품 속성 필터는 1~8개여야 합니다.")
            if any(not isinstance(k, str) or not IDENTIFIER.fullmatch(k) or
                   not isinstance(v, str) or not 1 <= len(v) <= 80 or
                   not re.fullmatch(r"[A-Za-z0-9 ._:/+-]+", v)
                   for k, v in rate["filters"].items()):
                raise ValueError("Price List 상품 속성이 올바르지 않습니다.")
            if "regionCode" in rate["filters"] and rate["filters"]["regionCode"] != doc["region"]:
                raise ValueError("단가 조회 리전과 사용량 리전이 일치해야 합니다.")
    return doc


def _price_from_response(response, unit, region):
    """정확히 하나의 SKU/단일 무조건 온디맨드 단가일 때만 계산 가능."""
    if response.get("NextToken") or len(response.get("PriceList", [])) != 1:
        return None, "상품 후보가 다수이거나 일부만 조회되었습니다."
    raw = response["PriceList"][0]
    record = json.loads(raw) if isinstance(raw, str) else raw
    if record.get("product", {}).get("attributes", {}).get("regionCode") != region:
        return None, "상품 리전이 일치하지 않습니다."
    terms = record.get("terms", {}).get("OnDemand", {})
    dims = []
    for term in terms.values():
        dims.extend(term.get("priceDimensions", {}).values())
    matches = [d for d in dims if d.get("unit") == unit and
               d.get("beginRange") in ("0", 0) and d.get("endRange") == "Inf" and
               d.get("pricePerUnit", {}).get("USD") is not None]
    if len(matches) != 1 or len(dims) != 1:
        return None, "단가가 계층화되어 있거나 여러 가격 차원이 존재합니다."
    value = Decimal(str(matches[0]["pricePerUnit"]["USD"]))
    if not value.is_finite() or value < 0:
        return None, "유효한 달러 단가가 아닙니다."
    return value, None


def _live_price(rate, unit, region, client):
    filters = dict(rate["filters"])
    filters["regionCode"] = region
    response = client.get_products(
        ServiceCode=rate["service_code"], FormatVersion="aws_v1", MaxResults=20,
        Filters=[{"Type": "TERM_MATCH", "Field": k, "Value": v}
                 for k, v in sorted(filters.items())],
    )
    return _price_from_response(response, unit, region)


def estimate_costs(config, *, live=False, client=None):
    """서비스별 추정 비용. 누락된 가격이 있으면 월간 총액은 null."""
    if isinstance(config, dict) and config.get("schema_version") == "2.0":
        try:
            from .cost_scenarios import estimate_scenarios
        except ImportError:
            from cost_scenarios import estimate_scenarios
        return estimate_scenarios(config, live=live, client=client)
    if config is None:
        return {"status": "needs_input", "complete": False, "currency": "USD",
                "region": None, "monthly_total_usd": None, "priced_subtotal_usd": None,
                "lines": [], "unpriced_count": 0,
                "note": "사용량 시나리오를 입력하지 않았습니다. AWS 예상 청구액은 산정하지 않았습니다."}
    if live and client is None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise ValueError("실시간 가격 조회에는 boto3가 필요합니다.") from exc
        client = boto3.client("pricing", region_name="us-east-1",
                              config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 1}))
    subtotal = Decimal("0")
    lines = []
    for item in config["items"]:
        rate = item["rate"]
        unit_price = None
        reason = None
        origin = rate["kind"]
        if origin == "manual_quote":
            unit_price = Decimal(str(rate["unit_price_usd"]))
        elif origin == "aws_price_list":
            if live:
                try:
                    unit_price, reason = _live_price(rate, item["unit"], config["region"], client)
                except Exception:
                    # 자격증명 오류/응답 본문/계정 식별자를 산출물에 노출하지 않음
                    reason = "AWS 가격표 조회에 실패했습니다. 권한/네트워크/상품 필터를 점검하세요."
            else:
                reason = "AWS 가격 조회가 비활성화되었습니다. --live-pricing을 명시하세요."
        else:
            reason = "가격 근거가 입력되지 않았습니다."
        amount = (unit_price * Decimal(str(item["quantity"]))) if unit_price is not None else None
        if amount is not None:
            subtotal += amount
        lines.append({
            "id": item["id"], "unit": item["unit"], "quantity": str(item["quantity"]),
            "rate_source": origin, "unit_price_usd": str(unit_price) if unit_price is not None else None,
            "monthly_amount_usd": str(amount) if amount is not None else None,
            "status": "estimated" if amount is not None else "unpriced",
            "reason": reason,
            "source_reference": (rate["source"] if origin == "manual_quote" else
                                 rate["service_code"] if origin == "aws_price_list" else None),
            "price_as_of": rate.get("as_of"),
        })
    unpriced = sum(x["status"] == "unpriced" for x in lines)
    complete = bool(lines) and unpriced == 0
    return {
        "status": "scenario_estimate" if complete else "partial_unpriced",
        "complete": complete, "currency": "USD", "region": config["region"],
        "monthly_total_usd": str(subtotal) if complete else None,
        "priced_subtotal_usd": str(subtotal) if lines else None,
        "lines": lines, "unpriced_count": unpriced,
        "note": "이는 입력 시나리오의 단순 곱셈입니다. 빠진 서비스, 무료/할인 한도,"
                "세금, 데이터 전송 및 요청량 변동에 따른 실제 청구액과 다릅니다.",
    }


def markdown_cost(report):
    rows = ["# AWS 비용 시나리오 검토", "",
            "> **실제 청구액이 아닙니다.** 입력된 사용량과 확인 가능한 단가만 계산합니다.",
            "", "- 상태: " + report["status"],
            "- 월간 총액(모든 항목 가격 확인 시만 표시): " +
            (report["monthly_total_usd"] or "미산정"), ""]
    rows += ["| 항목 | 사용량 | 단위 | 근거 | 예상 비용 USD | 상태 |",
             "| --- | ---: | --- | --- | ---: | --- |"]
    for x in report["lines"]:
        rows.append("| " + x["id"] + " | " + x["quantity"] + " | " + x["unit"] +
                    " | " + x["rate_source"] + " | " +
                    (x["monthly_amount_usd"] or "미산정") + " | " + x["status"] + " |")
    rows += ["", report["note"], "",
             "추가 점검: 리전별 상품 단가, 서비스별 차원·계층 요금,"
             " 네트워크 전송, 로깅, 저장, 백업, NAT, 라이선스, 세금/할인.", ""]
    if "scenarios" in report:
        try:
            from .cost_scenarios import scenario_markdown
        except ImportError:
            from cost_scenarios import scenario_markdown
        rows += ["", scenario_markdown(report)]
    return "\n".join(rows)
