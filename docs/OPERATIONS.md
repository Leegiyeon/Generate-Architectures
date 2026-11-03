# AWS 보안·트래픽·운영 설계 가이드 — Issue #13

> **중요:** 이 가이드는 GitHub 소스와 사용자가 명시한 조건으로 AWS 구축 전에 검토할 운영 청사진을 제안합니다. 실제 IAM/SG/암호화/CloudWatch/Auto Scaling/백업을 설정하거나 점검하지 않습니다. 테스트 통과는 프로덕션 적합성 판정이 아닙니다.

## 1. 제품 사용자에게 제공하는 내용

security-operations.json/md는 AWS To-Be 토폴로지에 등장하는 서비스에 한정해 다음을 정리합니다.

| 주제 | 대상 | 사용자에게 제공 | 수행하지 않는 일 |
| --- | --- | --- | --- |
| 보안 | ALB, ECS, Lambda, S3, RDS, IAM | SG 최소 통신 범위, 내부/외부 공개 경계, IAM 권한 분리, 민감정보·Secret 관리 확인 항목 | IAM 정책/보안그룹 적용, 암호화 적합성 검증 |
| 트래픽·성능 | ECS / ALB 또는 Lambda | 피크 RPS/지연 목표 입력값, 후보 스케일 지표, 쿼터·부하검증 필요 여부 | CPU/요청량 임계값, 용량/동시성 및 비용을 임의 확정 |
| 모니터링 | CloudWatch | 대상 서비스에 맞는 지표·알람 후보와 실제 임계값 검증 절차 | 계정의 경보를 생성하거나 실측 데이터를 가져오기 |
| 안정성 | Multi-AZ ECS/RDS, S3/DynamoDB | 단일 장애점·백업·복원·Failover 제안, RTO/RPO 원문 유지 | SLA/RTO/RPO 준수·장애복구 성능 보장 |
| 운영 | 배포·릴리스·런북 | 배포 검증·롤백·사고 대응/담당자 정책 | 배포 및 운영 자동 수행 |

## 2. 트래픽/Auto Scaling

average_rps, peak_rps, peak_concurrent_connections, latency_target_ms의 명시적 값만 실제 사용자 요구로 간주합니다.

- **ECS Fargate**: ECSServiceAverageCPUUtilization, ECSServiceAverageMemoryUtilization, ALBRequestCountPerTarget을 후보로 제공합니다. Target tracking에 적용할 최소·최대 Task 수와 타깃값은 실제 부하 시험과 태스크/타깃 그룹 구성이 확인되기 전까지 null로 유지합니다.
- **API Gateway + Lambda**: ConcurrentExecutions/Errors/Duration/Throttles 관련 지표와 서비스 동시성 제한·쿼터 확인을 제안합니다. API Gateway 요청 제한, 예약 동시성, 콜드스타트 목표를 무조건 확정하지 않습니다.
- **정적 서비스**: CloudFront 오류율·캐시/오리진 요청량의 관측을 제안하되 서버용 ECS Auto Scaling을 생성하지 않습니다.

특히 ALBRequestCountPerTarget은 단순 초당 RPS가 아니라 단위/타깃 그룹의 실제 집계 방식에 맞춰 조정해야 합니다. 개발 환경에서 측정한 수치를 운영 환경에 복사하지 마세요.

## 3. Security Group·IAM·Secrets

network-policy.md의 ALB→ECS→RDS 연결과 security-operations.json의 보안 통제 제안이 충돌하면 분석 결과를 오류로 처리합니다.

- Public ALB인 경우 TLS 인증서·ACM/WAF/보안그룹 인입·DNS를 확인합니다. Internal ALB는 클라이언트 VPN/전용망 경로를 별도로 검토합니다.
- ECS와 RDS를 인터넷에 직접 공개하지 않고 서비스별 SG 참조 통신을 검토합니다. 실제 인바운드 포트가 미확정이면 null로 둡니다.
- 앱 실행 역할과 관리/배포 역할을 구분하고 필요한 AWS API만 허용합니다.
- AWS Secrets Manager/SSM Parameter Store/KMS·암호화와 로그 마스킹은 선택과 운영 정책 제안일 뿐 실제 설정/Compliance 판정이 아닙니다.

## 4. 장애 복구 및 유지보수

사용자가 availability_target_percent, rto_minutes, rpo_minutes를 제공하면 보고서에 입력값 그대로 기록합니다. 구성에 Multi-AZ standby를 제안하더라도 실제 AWS 계정에 구현/검증됐다고 처리하지 않습니다.

- ECS: 두 논리 AZ에 작업 제안 시 대상 그룹 상태·최소 용량·장애 전환과 트래픽 부하 검증이 필요합니다.
- RDS: 백업 보관·PITR/스냅샷·암호화·복원 시험과 연결 정책을 검토합니다. RDS Multi-AZ standby는 읽기 트래픽 처리 전용 Replica가 아닙니다.
- 배포: 정상 동작/헬스체크, 점진적 배포, 오류 시 롤백 및 담당자 연락망이 필요합니다.
- 운영자: 장애 대응 런북, 장애 통지 기준, 감사 로그 및 보관·삭제 정책이 필요합니다.

## 5. Well-Architected 6개 원칙

| 원칙 | 이 설계 초안이 제공하는 것 |
| --- | --- |
| 운영 우수성 | 배포·롤백·사고 대응·로깅과 보관 |
| 보안 | IAM·SG 경계·비밀정보·민감정보·사용자 인가 |
| 안정성 | 다중 AZ 제안·백업·RTO/RPO·복구 연습 |
| 성능 효율성 | 피크 RPS·Auto Scaling 지표·부하/쿼터 확인 |
| 비용 최적화 | AWS 청구서·요금/리전 검증·NAT/로그/백업 비용 추적 |
| 지속 가능성 | 과잉 리소스/로그 보관 감축과 사용량 모니터링 |

모든 원칙은 review_required 상태이며, 자동으로 안전/성공/준수라고 표시하지 않습니다.

## 6. 완료 전 확인해야 할 사항

최소 운영 승인에 필요한 항목: 실제 서비스 소유자 및 책임자, AWS IAM/SG/라우트 실현 여부, 계정별 쿼터, 실측 트래픽·장애 복구 시험, 복구 목표, 보안·개인정보 규정, 배포 정책, AWS 비용과 데이터 보존 전략입니다.

이 제품은 AWS 계정 자격증명을 수집하지 않습니다. 향후 Local Inspector(#17)가 구축되더라도 로컬 AWS Profile/SSO 기반 읽기 전용 진단과 결과 접근 제어를 기본으로 합니다.

## 공식 AWS 참고

- [Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)
- [ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [ECS Target Tracking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html)
- [Lambda concurrency monitoring](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-concurrency.html)
- [Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html)
- [RDS backup and restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html)
