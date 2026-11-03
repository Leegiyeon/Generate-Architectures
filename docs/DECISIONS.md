# AWS Architecture Decision Engine — 서비스별 선정·제외 근거

> **제품 역할:** 저장소 분석 → 사용자 요구 → AWS 참조 설계 초안을 결정한 후, 그 이유와 유효하지 않은 대안, 아직 확인되지 않은 조건을 별도의 검토 자료로 제시합니다. AI 의견·실측 비용·실제 AWS 계정 상태를 대신하여 자동 승인하지 않습니다.

## 1. 현재 제공 범위

\`scripts/architecture_decision_engine.py\`가 다음 실행 패턴을 비교합니다.

| 후보 | 후보가 되는 이유 | 블로커/주요 확인 조건 |
| --- | --- | --- |
| Static: CloudFront + S3 | 서버 렌더링/백엔드가 필요 없는 정적 자산 | 실제 API 경로·SSR·데이터 처리 요구가 있으면 단독 정적 배포 차단 |
| Serverless: API Gateway + Lambda | 요청/이벤트 기반 API의 운영 부담 완화 | 호스트 제어·장시간 작업, 현재 DynamoDB 지향 템플릿과 관계형 DB 요구 충돌 |
| Container: ALB + ECS Fargate | Docker 기반 API 또는 지속 실행 프로세스 | 호스트 직접 제어 요구 시 차단. 이미지/포트/SG/Private outbound 별도 검토 |
| Amazon EC2 (+ ALB) | 직접 OS 제어·기존 레거시 실행 필요 | OS·패치·AMI·접근제어·Auto Scaling 관리 부담; **현재 자동 To-Be 도식에는 미포함** |
| 모바일 API | 모바일 클라이언트의 인증/백엔드 | 모바일 요구 없으면 미적용; RDS/호스트 제어 요구는 현재 템플릿에 없음 |

정적 분석으로만 단정할 수 없는 최대 작업 지속시간, 피크 처리량, 운영역량, 기존 DB의 연결 방식을 구분합니다. **EC2는 비교 후보**이지 사용자가 승인하지 않은 자동 변경 대상이 아닙니다.

\`max_job_duration_seconds\`가 900초를 초과하면 현재의 **일반 Lambda 기반** 참조 템플릿을 차단합니다. AWS는 일반 Lambda 함수의 최대 실행 제한을 900초로 설명하지만, 2026년 기준 일부 **Lambda Managed Instances의 비동기/이벤트 호출**에는 5,400초 예외가 있습니다. 따라서 이는 **모든 Lambda 제품이 불가능하다는 판정이 아니라 현 템플릿과 조건의 충돌**입니다. 정확한 호출 종류·할당량·API Gateway 타임아웃은 별도 검토해야 합니다.

참고: [AWS Lambda timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html), [ECS compute 선택](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-configuration.html).

## 2. 추가 요구사항

\`\`\`json
{
  "requires_host_control": false,
  "max_job_duration_seconds": 120,
  "average_rps": 10,
  "peak_rps": 300,
  "operations_preference": "balanced",
  "requires_relational_database": true
}
\`\`\`

위 값들은 **입력 형식 예시**이지 실제 프로젝트의 설정이 아닙니다. 운영 지표와 최대 작업시간을 확인할 수 없으면 입력하지 않고 검토 항목으로 남깁니다.

## 3. 결과물 및 승인 상태

- \`architecture-decision-matrix.json\`: 각 후보의 정적 블로커(\`blockers\`), 미확인 조건(\`review_required\`), 근거 ID(\`evidence_ids\`), 운영 트레이드오프, 비용/성능 미검증 상태.
- \`architecture-decision-matrix.md\`: **한국어 비교표**, 현재 참조안 선정 이유, 대안과 제외 사유, 승인 전 확인 항목.
- \`recommendation.md\`: 현재 후보·차단 여부·추가 검토할 최대 두 개 후보 안내.
- \`validation.json\`: 현재 참조 패턴에서 명시된 블로커가 확인되면 \`DEC-001\`을 추가해 승인 전 자동 채택이 차단됩니다.

\`status=blocked_for_current_template\`는 **그 AWS 기술이 불가능하다는 판정이 아닙니다**. Lambda+RDS 등 다른 구성은 가능하지만 현재의 Lambda+DynamoDB 참고안은 관계형 DB 요구에 맞지 않는다는 뜻입니다.

비용/성능 수치가 충분하지 않아 **자동 점수, 우선순위 백분율, 예상 월 청구액**은 생성하지 않습니다. 현재 비교는 정적 근거와 확인된 요구사항에서 **설명 가능한 후보만 남기는 검토 과정**입니다.

## 4. 운영·보안

입력 원문·GitHub 인증키·AWS 비밀정보를 LLM으로 자동 전송하지 않습니다. AI 보조 검토가 켜져도 생성된 의견은 **독립된 AI 검토 보고서**에 보관하며, 이 후보 비교 결과·AWS To-Be 다이어그램·배포 작업을 자동 수정하지 않습니다.

**최종 승인권은 사용자에게 있으며**, 코드에서 확인한 사실·설정 단서·사용자 입력·기본값/가정을 명확히 구분합니다. 실제 비용·쿼터·부하·보안 검증을 마친 뒤 ADR을 승인하는 절차는 이후 단계의 범위입니다.

## 5. 다음 단계

- **#12 고도화:** EC2/Fargate/Lambda 서비스별 최종 연결 토폴로지, 장기 실행·배치와 이벤트 처리 복합 패턴, 데이터 저장소 대안 및 실제 사용사례 교차검증.
- **#13:** Well-Architected 관점의 보안·운영·오토스케일/용량·백업·복구 청사진.
- **#15:** 서비스별 공식 AWS 단가 기반의 최소/기준/피크 시나리오 비용 비교.

## 6. 데이터 접근·ADR·EC2 대안 (후속 개발)

`data_access_pattern`을 `undecided`, `relational_transactions`, `document_queries`, `key_value`에서 선택할 수 있습니다. RDS/DynamoDB/기존 MongoDB 유지/Amazon DocumentDB를 **선정 확정이 아닌 검토 대안**으로 비교합니다. `database_migration_approved=true`를 입력해도 DB 자동 이전이나 서비스 확정은 발생하지 않습니다. MongoDB와 Amazon DocumentDB의 쿼리·버전·드라이버 호환성은 독립 검증이 필요합니다.

`data-access-decision.json/md`는 데이터 액세스 특성과 전환 제약을, `decision-record.json/md`는 명시 입력/기본값·근거·검토 대안·차단 이유·승인 대기 상태를 기록합니다. 이전 `decision-record.md`가 모든 값(시스템 기본값 포함)을 사용자 입력으로 서술하던 문제를 수정했습니다.

Fargate가 선택된 경우 `ec2-alternative/`에서 **ASG + Private Subnet EC2 + ALB, 선택적 RDS**의 별도 논리 토폴로지를 제안합니다. EC2는 실제 인스턴스 타입·이미지·장애 복구·NAT·Route Table을 확정하지 않습니다. 기존 Fargate용 ECR/VPC Endpoint 설정이 EC2와 동일하다고 가정하지 않습니다.

> 상태: 모든 대안 **제안/미승인**. 실제 보안 점검이나 클라우드 배포 권한·승인은 별도로 관리해야 합니다.
