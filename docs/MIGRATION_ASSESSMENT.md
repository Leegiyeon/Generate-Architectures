# AWS 이전 전략 비교 (Migration Assessment) — 검토 초안

**대상:** GitHub 저장소에 애플리케이션 코드가 있고 기존 서버·DB를 온프레미스에서 운영하는 사용자. **Rehost(EC2 중심)**와 **Replatform(ECS/RDS 등)**의 차이 및 주요 위험을 사람이 비교할 수 있게 돕습니다.

> **이 기능은 실제 이전 가능성 인증/마이그레이션 실행이 아닙니다.** 소스코드의 정적 단서와 **사용자가 입력한** As-Is 정보만 사용합니다. AWS 계정/온프레미스 서버에 접속하지 않습니다.

## 사용 — 기존 과정 그대로

1. 저장소에 [예시 Workflow](../examples/aws-architecture.yml)를 추가하고, [최소 Inventory JSON](../examples/onprem-inventory.example.json)을 `.architecture/onprem-inventory.json`에 저장합니다.
2. Actions → AWS Architecture Review → Run workflow → `migrate_onprem`을 선택합니다. **추가 필수 입력은 없습니다.**
3. Artifacts의 `START-HERE.html`에서 As-Is, AWS To-Be, **Rehost / Replatform 변경사항·위험**을 확인합니다. 기술 상세는 `migration-assessment.md`와 `migration-assessment.json`에 있습니다.

Inventory가 없으면 기존처럼 **현재 구성 미확인/전략 비교 보류**로 표시합니다. Rehost가 자동으로 안전하다거나 관리형 DB로 전환할 수 있다고 가정하지 않습니다.

## 무엇을 비교하나요?

| 기존 구성(사용자 선언) | Rehost 후보 | Replatform 후보 | 실제 확인할 사항 |
| --- | --- | --- | --- |
| Linux 웹/API | EC2에서 실행 환경 유지 검토 | 컨테이너 단서가 있으면 ECS Fargate, 없으면 컨테이너화 가능성부터 확인 | 런타임·상태/파일 경로·이미지 빌드·확장·AMI/OS 패치 |
| PostgreSQL/MySQL 등 | 기존 DB 엔진을 EC2에서 유지하는 이전 방법 검토 | **동일 엔진** Amazon RDS 검토 후보 | 버전·확장/권한·백업·복구·데이터 동기화·라이선스 |
| Windows·OS 미확인 | OS 호환/라이선스가 확인돼야 EC2 검토 | ECS/Fargate 지원·제약 확인 전 **자동 전환 보류** | 설치/지원 조건, 드라이버, 운영 책임 |
| MongoDB | EC2/기존 엔진 유지 검토 | DocumentDB 자동 전환 금지, 호환성 검사 선행 | API/인덱스/드라이버/데이터 |
| 기존 파일 스토리지 | EBS/EC2 내 저장 방식 검토 | EBS/EFS/S3 후보를 **접근 방식 확인 후** 결정 | POSIX·공유 잠금·객체 접근 및 데이터 이전 |
| 기존 프록시 | EC2에 기존 라우팅 유지 검토 | ALB 검토 후보 | URL rewrite/TLS/인증/헤더/Health Check |

**이 표는 AWS 공식 제품 선택을 인증하는 비교표가 아닙니다.** 사용자가 선언한 서버 역할·DB 종류와 저장소에서 실제 관측한 단서에 따라 후보별로 다르게 출력됩니다. AWS To-Be 참조도가 ECS라고 해서 기존 서버를 모두 ECS로 전환한다고 결정하지 않습니다.

## 서버 간 연결의 변경 검토

각 전략의 `connection_changes`에는 **Inventory에 선언된 연결만** 같은 방향의 `from`/`to`/`purpose`로 보존합니다. 기존 서버별 `changes`의 후보를 `from_candidates`/`to_candidates`에 연결하며 서버 변경표의 구조는 유지합니다. Markdown에는 별도 연결 비교표를 제공합니다.

- **Rehost — 유지 검토(`retain`)**: 양쪽 서버가 EC2 후보로 대응되고 연결 목적이 대상 역할·DB 선언과 맞으면 선언된 논리 관계를 유지하는 방안을 검토합니다. 실제 주소·경로를 그대로 유지할 수 있다는 판정이 아닙니다.
- **Replatform — 변경 검토(`modify`)**: 양쪽 서버가 각각 단일 구성요소 후보로 대응되고 연결 목적이 맞으면 후보 서비스에 따른 접속 경로 변경을 검토합니다. 실제 접근 경로·연결 가능성은 확정하지 않습니다.
- **미확인(`unknown`)**: 목적이 `other`이거나 목적과 대상 역할이 맞지 않는 경우, 서버 후보가 미확정인 경우, 혼합 서버가 앱·DB 등 여러 후보로 나뉘는 경우입니다. `database` 목적만으로 혼합 서버 안의 실제 출발·도착 구성요소를 선택하지 않습니다. Inventory에서 허용하지 않는 목적 `unknown`이나 미등록/누락 endpoint는 기존 입력 검증에서 거부합니다.

연결마다 `as-is-inventory.json#/connections/N` 출처를 남기고 각 endpoint 후보에도 기존 서버·코드 근거를 보존합니다. `N`은 생성된 **정규화 Inventory**의 연결 순서입니다. 선언이 없으면 빈 배열이며 실제 연결이 없다는 의미가 아닙니다. 새 연결·포트·프로토콜·보안그룹·DNS·인증 설정은 추정하지 않습니다. `validated=false`, `change_approved=false`, `network_verified=false`는 두 전략 모두 유지합니다. 유지/변경 분류는 실제 네트워크 검증, 이전 가능성 또는 운영 승인을 뜻하지 않습니다.

## 위험과 근거

각 서버/구성요소별 변경에는 `user_declared_unverified` 기반 `as-is-inventory.json#/servers/N` 등 **원본 증거 위치**를 남깁니다. Docker·DB 관련 코드 단서가 있다면 `repository_code_signal`로 따로 표시합니다. 코드에서 라이브러리를 발견한 사실로 실제 DB 호스트, 네트워크, 데이터 크기를 추측하지 않습니다.

위험은 정보 미확인·데이터 무결성·외부 연동/인증·OS/라이선스·기존 하드웨어 의존·보안·VPN/Direct Connect 검토·복구 목표·다운타임 및 비용/용량을 다룹니다. 일부 위험은 차단 대상으로 표시하지만 이는 **정적 검토에서 추가 확인이 필요하다는 의미**이며, AWS에서 검증·반려한 결과가 아닙니다.

기존 서버의 `storage_gb`는 **총 디스크 용량**이지 실제 DB 크기나 복사 예상 시간이 아닙니다. `rto_minutes`/`rpo_minutes`를 입력했어도 목표 달성 여부는 별도 복구 시험이 필요합니다. **다운타임·전체 마이그레이션 비용·예상 필요 인스턴스 수는 추정하지 않고 미산정**으로 남깁니다.

## 6단계 검토 체크리스트 (자동 실행 없음)

1. **사전 조사**: 현재 OS/DB/미들웨어 버전·데이터 실크기·네트워크·의존성·라이선스·정책·책임자 파악.
2. **시험 환경 검증**: AWS 시험 환경에 앱/DB·보안/서비스 성능·로그/알람을 구현해 기능·부하 검증.
3. **데이터 이전 계획**: DB/파일 초기 복제·증분 동기화·암호화 및 무결성 검증과 복원 절차 작성.
4. **전환 전 확인**: 기능/데이터 일치·감사/접속·장애 복구/백업 복원 시험 및 사람 승인.
5. **서비스 전환(Cutover)**: 승인된 작업창·DNS/라우팅 변경·관측 및 실패 판단 기준을 수동 수행.
6. **롤백(Rollback)**: 서비스 원복과 데이터 역동기화/손실 예방의 실행 가능성·책임자 확인.

각 절차의 **완료 여부를 자동 표시하지 않으며** 실제 AWS MGN, DMS, Schema Conversion, DNS 변경, 데이터 복제, Terraform 적용을 실행하지 않습니다.

## 결과의 한계·비용

- `recommended_strategy=null`, `migration_approved=false`, `migration_ready=false`: 자동 최적 전략 선정·실제 승인 없음.
- `estimated_monthly_migration_cost_usd=null`, `cutover_downtime_minutes=null`: 실제 AWS 단가/계정·데이터 이전 시간 미검증.
- `migration_review_generated=true`는 오직 **정적 검토 초안이 생성됨**을 의미합니다.
- 입력 Inventory가 없으면 `needs_inventory`로 마이그레이션 비교가 생성되지 않습니다.
- 기존 AWS 비용 분석 결과를 Rehost와 Replatform의 총비용으로 자동 복제하거나 두 후보의 가격 차이를 단정하지 않습니다.

AWS 공식 참조: [AWS Prescriptive Guidance — 7 Rs](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html), [애플리케이션 포트폴리오 이전 분석](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-portfolio-playbook/discovery.html).

**보안:** Inventory에는 비기밀 별칭만 사용하세요. GitHub Actions Artifacts에는 조직 내부 자산의 개략 구성이 포함되므로 저장소 접근 권한과 Artifact 노출 범위를 검토해야 합니다.
