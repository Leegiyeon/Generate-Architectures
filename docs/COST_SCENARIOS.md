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

- AWS 실제 SKU/상품 그룹별 요금 차원·계층형(Tiered) 가격/무료 한도 처리 및 AWS 공식 산술 사례 검증
- 동일 워크로드 기준 ECS/EC2/Lambda 대안의 규모·할당량과 리전별 이용 가능성 대조
- CPU·메모리·동시성 실측을 피크 RPS와 연결한 정량 추정 및 신뢰도 검증

가격을 임의 입력하거나 근거 없는 월 총액/서비스별 우열을 생성하지 않습니다.
