# 동일 업무량 AWS ECS Fargate / EC2 / Lambda 비용·운영 책임 비교

> **제품 범위:** 사용자가 직접 기입한 월 요청량과 후보별 AWS 서비스·월 사용량·단가만 비교합니다. 동일한 처리 성능, 기능·보안·SLO 적합성을 검증하거나 최적 서비스/최저 비용을 자동 선정하지 않습니다. AWS 계정 접근·배포·리소스 변경 없음.

## 1. 시작하기

[예제 입력](../examples/alternative-cost-comparison.example.json)의 요청 수·vCPU·GB·시간 수치는 모두 가상 예시이며, 모든 가격을 unknown으로 비워 두었습니다. 단가를 확인하여 입력하지 않으면 비용은 미산정으로 표시됩니다.

CLI: python3 scripts/recommend_architecture.py --repo . --output architecture-output --requirements .architecture/requirements.json --alternative-cost-input examples/alternative-cost-comparison.example.json

GitHub Actions: Actions → AWS 아키텍처 검토 자동화 → Run workflow → alternative_cost_input에 저장소 내부 비기밀 JSON 파일 경로 입력. 미입력 상태에서는 needs_input 상태를 명시하고 거짓 가격을 생성하지 않습니다.

AWS 실시간 요금 조회는 사용자가 별도로 live_pricing=true를 지정한 경우에만 실행합니다. 저장소에 AWS 키·임시 크리덴셜 또는 실계정 설정을 저장하지 마세요.

## 2. 입력 계약

schema_version 1.0에 다음 내용을 입력합니다.

- region: 모든 후보가 동일한 AWS 리전의 가격만 비교하도록 공통 지정합니다.
- workload: 하나의 ID와 minimum/baseline/peak 월 요청 수, peak_rps를 한 번만 정의합니다. 이 값은 모든 후보에 공통으로 사용되며, 요구사항 파일의 expected_monthly_requests / peak_rps / region과 충돌하면 비교하지 않습니다.
- shared_items: 후보에 공통으로 포함하는 데이터 전송·CloudWatch 로그 등 항목. 후보별 중복 계산 금지.
- candidates: fargate / ec2 / lambda 중 서로 다른 2~3개. 각 후보의 items에 실제 검토한 월 사용량과 요금표/단가 출처를 입력합니다. 항목별 단가/단위/사용량은 기존 비용 v2 포맷을 따릅니다.

요청 수가 같더라도 Fargate의 vCPU-Hours·GB-Hours, EC2의 인스턴스 시간·EBS, Lambda의 Requests·GB-Seconds를 같게 취급하지 않습니다. 실제 피크 RPS를 처리하기 위한 용량·대상 그룹·동시 실행 수는 반드시 부하 테스트로 결정해야 합니다.

## 3. 비용 및 운영 검토

산출물: alternative-cost-comparison.json/md, 사용자 START-HERE.html의 비용 비교 표, deliverables/04-cost-capacity.md의 상세 비교.

- 동일 업무량·리전·요구사항 충돌 시 상태 requirements_mismatch.
- 각 후보의 필수 비용 분류가 비어 있으면 missing_service_cost_categories. Fargate는 ECS/ALB, EC2는 EC2/ALB, Lambda는 Lambda/API Gateway 외에 데이터 전송·CloudWatch 로그 범주를 요구합니다.
- 기존 아키텍처 결정 규칙의 블로커가 있으면 blocked_by_constraints. 가격이 저렴해도 요구사항을 충족한다고 인정하지 않습니다.
- 실제 단가가 비어 있으면 partial_unpriced. 누락 항목을 0달러로 계산하지 않습니다.
- 가격·기본 비용 분류·업무량·요구가 일치하는 경우만 modeled_items_comparable_unverified 상태로 입력된 항목의 차액을 표시합니다. 이 차액은 실제 AWS 청구 차이가 아닙니다.

각 서비스는 운영 책임이 다릅니다. Fargate는 컨테이너 이미지/태스크·Task Role·ECS Auto Scaling, EC2는 OS/AMI 패치·EBS/SSM·Instance Profile·Auto Scaling, Lambda는 함수/호출·타임아웃/동시성·함수별 IAM/비밀정보·API Gateway 정책을 별도 검토해야 합니다.

## 4. 가격·성능 한계

AWS 공식 설명에 따르면 Fargate의 CPU/메모리/추가 스토리지, EC2의 인스턴스 시간과 부가 EBS·데이터 전송, Lambda의 요청/실행시간 등은 서로 다른 과금 요소입니다. 실제 SKU/무료 한도·할인·계정 집계, ALB LCU·RDS·NAT·보안/관측·백업 및 네트워크 비용이 일부 빠질 수 있으므로 **전체 비용이나 최적 AWS 서비스라고 표시하지 않습니다.**

공식 가격 근거:
- https://aws.amazon.com/fargate/pricing/
- https://aws.amazon.com/ec2/pricing/on-demand/
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/api-gateway/pricing/

실제 서비스 이전 검토는 API/DB 기능 동등성, 트래픽/부하·Service Quotas, RTO/RPO, IAM·SG·암호화·운영자 패치 책임과 해당 지역 가격을 확인한 후 사람이 승인해야 합니다.

## 제출된 부하 테스트와의 연결 (#15 4차)

선택형 capacity_evidence 파일을 함께 입력하면 동일 workload_id·AWS 리전·peak_rps·후보 구성이 일치하는지 확인합니다. 제출된 집계 처리량, p95 지연, 오류율, 시험 시간 중 하나라도 기준에 못 미치면 기존 입력 비용 모델의 차액 비교를 보류하며 capacity_evidence_review_required로 표시합니다. 모든 조건을 만족하더라도 실제 운영 성능/계정 쿼터는 검증되지 않았으므로 여전히 입력 항목의 산술 차액만 표시합니다. [부하 테스트 집계 입력 규격](CAPACITY_EVIDENCE.md).
