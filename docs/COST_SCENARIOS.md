# AWS 비용·용량 3시나리오 — Issue #15 (기반 구현)

> 이 기능은 **사용자 입력 월 사용량 × 검증 가능한 AWS 출처 단가**만 계산합니다. 전체 AWS 청구액/실측 성능/인프라 자동 생성이 아닙니다.

## 사용법

[예제 JSON](../examples/cost-scenarios.example.json)을 복사해 서비스별 minimum/baseline/peak 사용량과 실제 확인된 AWS 단가를 채웁니다. 예제 사용량은 가상 수치이며 모든 단가가 unknown이므로 기본 비용은 미산정됩니다.

CLI 실행: `python3 scripts/recommend_architecture.py --repo . --output architecture-output --cost-input examples/cost-scenarios.example.json`

GitHub Actions 수동 실행 시 cost_input 항목에 예시 파일 경로를 입력할 수 있습니다. 실시간 AWS 가격 조회를 명시적으로 동의한 경우에만 --live-pricing이 작동합니다. AWS 자격증명 파일을 커밋하거나 요구사항 JSON에 저장하지 마세요.

## v2 입력 형식

```json
{
  "schema_version": "2.0",
  "region": "ap-northeast-2",
  "items": [
    {
      "id": "alb_hours",
      "service": "alb",
      "unit": "Hrs",
      "quantities": {"minimum": 100, "baseline": 500, "peak": 730},
      "rate": {"kind": "unknown"}
    }
  ]
}
```

- service: alb, ecs_fargate, rds, ec2, cloudfront, s3, api_gateway, lambda, dynamodb, cognito, nat_gateway, vpc_endpoints, data_transfer, cloudwatch_logs, backup_storage, other 중 하나.
- quantities: 최소 ≤ 기준 ≤ 피크, 0 이상. 프로젝트의 RPS로 월 사용량을 임의 변환하지 않습니다.
- rate: 기존의 unknown / manual_quote(AWS 공식 HTTPS 출처, 일자·단가) / aws_price_list(정확한 SKU 필터, 명시적 live-pricing) 형식 그대로.
- region: AWS To-Be 설계 리전과 요금 리전을 대조하며, 실제 SKU/가격 차원과 차액이 검증된 것은 아닙니다.

기존 단일 사용량 방식 v1은 완전한 하위 호환을 유지합니다.

## 결과와 해석

cost-estimate.json/md, deliverables/04-cost-capacity.md, START-HERE.html에 3개 시나리오별 가격 확인 **부분합**, 모든 입력 항목 계산 시 합계, 단가 누락 개수를 제공하며 계산 근거가 없으면 null/미산정으로 남깁니다.

topology_coverage는 AWS To-Be에 있는 ALB, ECS, RDS, Lambda, NAT/Endpoint, 데이터 전송, CloudWatch 로그, 백업 등의 **비용 분류가 비용 입력에 존재하는지**를 확인합니다. 분류가 모두 있어도 실제 계정의 SKU/청구액/용량을 증명하지 않습니다. complete_for_entire_architecture는 항상 false입니다.

ALB는 시간당 요금 외 LCU 등 별도 차원이 있을 수 있고 RDS는 DB 인스턴스/스토리지/IO/백업 등 복합 요금이 필요할 수 있으므로 실제 계약 조건과 AWS Calculator를 대조해야 합니다.

공식 참고:
- https://aws.amazon.com/aws-cost-management/aws-pricing-calculator/
- https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html

## 후속 개발 (#15 미완료)

- 계층형 단일 SKU 요금은 **연속 구간에 한해 구현**, 공식 계정 데이터와 교차 SKU·프리티어·집계 요금의 실제 청구 검증 미완료
- 동일 워크로드 기준 ECS/EC2/Lambda 대안의 규모·할당량과 리전별 이용 가능성 대조
- CPU·메모리·동시성 실측을 피크 RPS와 연결한 정량 추정 및 신뢰도 검증

가격을 임의 입력하거나 근거 없는 월 총액/서비스별 우열을 생성하지 않습니다.

## Price List Query API 계층 요금 해석 — 2차 구현

AWS 공식 [Price List의 티어 문서](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/finding-prices-in-service-price-list-files.html)는 하나의 SKU/OnDemand term에서 `priceDimensions`의 `beginRange`·`endRange`마다 USD 단가를 제공한다고 설명합니다.

비용 시나리오 v2에서는 `live_pricing=true`를 명시한 경우에만 `GetProducts`를 조회하며, 가격표에 **정확한 SKU 하나, 온디맨드 조건 하나, 동일 청구 단위, 연속되는 범위 0→Inf**가 존재할 때 다음 공식을 적용합니다.

```text
월 입력 사용량 Q
각 구간 사용량 = max(0, min(Q, endRange) - beginRange)
구간별 USD = 각 구간 사용량 × pricePerUnit.USD
월 입력 항목 비용 = 모든 구간별 USD 합계
```

예를 들어 **가상 수치**인 0~100 요청에 $0.20, 100~∞ 요청에 $0.10이라면, 150건은 100×0.20+50×0.10=$25입니다. **실제 AWS 요금이 아닙니다.**

유효하지 않은 SKU/다수 상품·혼합 단위·중복/누락된 요금 구간·리전 불일치·결합형 프리티어 `appliesTo`·특별 계약 조건은 계산을 거부해 `unpriced`로 남깁니다. AWS Pricing Query API가 가격 차원에 계정 공유 무료 할당량/할인/약정 전체를 포함하는 것은 아니므로, 자동 적용하지 않습니다.

`cost-estimate.json`과 `cost-estimate.md`에는 지원되는 경우 각 항목의 **SKU, 요금 적용일(effectiveDate), 월별 수량, 구간별 USD 단가, 계산 방식과 실제 미산정 사유**를 남깁니다. 조회된 응답 본문/계정 ID·인증키는 기록하지 않습니다. 가격표를 조회하지 않으면 기본값대로 **미산정**됩니다.

**v1 단일 수량 형식은 기존 동작을 유지**하며 v1 계층 요금은 미산정입니다. 계층 해석은 현재 v2 입력 형식에 한정합니다. 여러 상품을 결합하는 스토리지/전송/요청 과금, AWS 전체 청구액, 공식 Pricing Calculator 실제 사례/운영 비용 대조는 아직 후속 검증 대상입니다.

공식 자료: [AWS GetProducts API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_pricing_GetProducts.html), [AWS 서비스 가격표 차원](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/reading-service-price-list-file-for-services.html).

## ECS Fargate / EC2 / Lambda 동일 업무량 비교 입력 (3차 기능)

이전의 단일 AWS 선택안 비용 시나리오와 별도로, 두 개 이상 실행 대안의 월 요청량을 공통으로 고정하고 각각의 서비스 사용량·요금 항목을 입력할 수 있습니다. 이는 피크 RPS를 CPU/메모리/동시 실행 수로 환산하는 것이 아니므로 실측 없이 성능 동등성을 주장하지 않습니다. [예제 JSON](../examples/alternative-cost-comparison.example.json)과 [상세 판정 기준](ALTERNATIVE_COST_COMPARISON.md)을 참조하세요. 결과는 `alternative-cost-comparison.json/md` 및 HTML 비용 영역에 추가됩니다.
