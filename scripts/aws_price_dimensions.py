"""AWS Price List Query API의 정확히 하나의 OnDemand SKU/단위 요금표 해석.

AWS 공식 GetProducts 구조를 근거로 beginRange / endRange 별 체증 요율만 계산.
계정 전체의 프리티어, 결합 계층, 계약 할인 및 다차원 SKU는 계산하지 않습니다.
원문 API 응답, 자격증명, 상품 설명을 산출물에 그대로 기록하지 않습니다.

문서: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/finding-prices-in-service-price-list-files.html
"""
from decimal import Decimal, InvalidOperation
import json
import re

MAX_DIMENSIONS = 20
NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
DATE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)?\Z")


def _number(raw):
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise ValueError("가격/계층 숫자 타입이 올바르지 않습니다.")
    value = str(raw)
    if NUMBER.fullmatch(value) is None:
        raise ValueError("계층 구간 또는 USD 요금이 유한한 양수 형식이 아닙니다.")
    try:
        dec = Decimal(value)
    except InvalidOperation:
        raise ValueError("가격/계층 숫자가 유효하지 않습니다.") from None
    if not dec.is_finite():
        raise ValueError("가격/계층 숫자가 유한하지 않습니다.")
    return dec


def interpret_price_dimensions(response, unit, region):
    """모호한 후보/사용량 티어/연결 무료 티어는 계산하지 않고 이유만 반환.

    응답에 하나의 SKU와 OnDemand term만 있을 경우, 모든 차원이 같은 단위이고
    0부터 Inf까지 계층 구간이 정확히 연속적이면 가격표를 사용할 수 있습니다.
    """
    failure = lambda message: {"status": "unpriced", "reason": message, "tiers": [],
                                "sku": None, "effective_date": None}
    if not isinstance(response, dict):
        return failure("AWS 가격표 응답 형식을 확인할 수 없습니다.")
    products = response.get("PriceList", [])
    if response.get("NextToken") or not isinstance(products, list) or len(products) != 1:
        return failure("SKU 후보가 중복되거나 가격 조회가 페이징되어 단일 SKU가 확정되지 않았습니다.")
    try:
        raw = products[0]
        rec = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(rec, dict):
            return failure("AWS 상품 레코드 형식이 올바르지 않습니다.")
        product = rec["product"]
        attributes = product["attributes"]
        if attributes.get("regionCode") != region:
            return failure("AWS Price List 상품의 리전이 요청 리전과 다릅니다.")
        sku = product.get("sku")
        if not isinstance(sku, str) or not IDENTIFIER.fullmatch(sku):
            return failure("AWS SKU 식별자가 없거나 유효하지 않습니다.")
        terms = rec["terms"]["OnDemand"]
        if not isinstance(terms, dict) or len(terms) != 1:
            return failure("동일 상품의 OnDemand 조건이 복수이거나 누락됐습니다.")
        term = next(iter(terms.values()))
        if not isinstance(term, dict) or term.get("termAttributes", {}) not in ({}, None):
            return failure("추가 계약 조건이 있는 요금표는 자동 계산하지 않습니다.")
        dimensions = term["priceDimensions"]
        if not isinstance(dimensions, dict) or not (1 <= len(dimensions) <= MAX_DIMENSIONS):
            return failure("요금 차원이 없거나 너무 많아 검증할 수 없습니다.")
        parsed = []
        for dim in dimensions.values():
            if not isinstance(dim, dict) or dim.get("unit") != unit:
                return failure("한 상품에서 서로 다른 청구 단위가 혼합돼 있습니다.")
            if dim.get("appliesTo") not in (None, []):
                return failure("특정 SKU/계정에 결합된 프리티어·계층 조건은 검증할 수 없습니다.")
            usd = dim.get("pricePerUnit", {})
            if not isinstance(usd, dict) or set(usd) != {"USD"}:
                return failure("단일 USD 요금 단위가 확정되지 않았습니다.")
            begin = _number(dim.get("beginRange"))
            end_raw = dim.get("endRange")
            end = None if end_raw == "Inf" else _number(end_raw)
            price = _number(usd["USD"])
            if end is not None and end <= begin:
                return failure("계층 구간 끝이 시작값 이하입니다.")
            parsed.append((begin, end, price))
        parsed.sort(key=lambda t: t[0])
        if parsed[0][0] != 0 or parsed[-1][1] is not None:
            return failure("가격 계층이 사용량 0부터 무한대까지 모두 정의되지 않았습니다.")
        for previous, following in zip(parsed, parsed[1:]):
            if previous[1] is None or previous[1] != following[0]:
                return failure("계층 구간이 중복되거나 빠져 있습니다.")
        effective = term.get("effectiveDate")
        if effective is not None and (not isinstance(effective, str) or
                                      not DATE_ISO.fullmatch(effective)):
            return failure("가격 적용 기준일 형식이 유효하지 않습니다.")
        return {
            "status": "priced", "reason": None,
            "sku": sku, "effective_date": effective,
            "price_model": "flat" if len(parsed) == 1 else "tiered_graduated",
            "tiers": [{"begin": str(begin), "end": str(end) if end is not None else "Inf",
                       "usd_per_unit": str(price)} for begin, end, price in parsed],
        }
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError, json.JSONDecodeError):
        return failure("가격표 필수 필드가 없거나 검증할 수 없는 계층 데이터입니다.")


def amount_for_tiers(tiers, quantity):
    """'사용량 구간별 누적 과금'만 계산; 계정 공유 프리티어/할인은 적용하지 않음."""
    remaining = _number(quantity)
    total = Decimal("0")
    for item in tiers:
        begin = _number(item["begin"])
        end = None if item["end"] == "Inf" else _number(item["end"])
        rate = _number(item["usd_per_unit"])
        upper = remaining if end is None or end > remaining else end
        if upper > begin:
            total += (upper - begin) * rate
    return total


def lookup_price_dimensions(rate, unit, region, client):
    """단일 GetProducts 요청 + 리전 고정; 자격증명·예외 응답 본문 외부 노출 금지."""
    filters = dict(rate["filters"])
    filters["regionCode"] = region
    try:
        response = client.get_products(
            ServiceCode=rate["service_code"], FormatVersion="aws_v1", MaxResults=20,
            Filters=[{"Type": "TERM_MATCH", "Field": key, "Value": value}
                     for key, value in sorted(filters.items())],
        )
        return interpret_price_dimensions(response, unit, region)
    except Exception:
        return {"status": "unpriced",
                "reason": "AWS 가격표 조회에 실패했습니다. 권한·네트워크·SKU 필터를 점검하세요.",
                "tiers": [], "sku": None, "effective_date": None}
