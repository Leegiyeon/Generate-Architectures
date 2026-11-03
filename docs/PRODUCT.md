# Generate-Architectures — 제품 정의 및 사용 범위

**목표:** 개발자가 GitHub 저장소를 한 번 분석해 AWS 참조 아키텍처와 서비스 선정 근거를 확인하고, 추가로 확인할 사항을 이해할 수 있도록 지원합니다. 앱의 핵심은 복잡한 설정이 아니라 **선택 1개 → 실행 → 한 장 보고서**입니다.

## 사용자 여정

1. 대상 저장소에 [예시 GitHub Workflow](../examples/aws-architecture.yml) 한 개 설치.
2. GitHub Actions에서 **분석 목적만 선택**합니다. `new_aws` 또는 `migrate_onprem`. 세부 요구사항 파일은 선택.
3. Artifacts의 **START-HERE.html**로 결과 확인 후 필요한 경우에만 입력 보완·재분석.

기본 실행은 사용자가 명시적으로 실행할 때만 이루어집니다. 본 저장소의 CI에서 push/PR 발생 시 자동 테스트하는 것과 **외부 저장소의 아키텍처 재분석**은 별도입니다.

## 현재 지원 기능과 한계

| 기능 | 지원 상태 | 주의할 점 |
| --- | --- | --- |
| 코드·설정 정적 분석 | 구현 | 실제 런타임·서버 위치·네트워크 연결을 관찰한 것은 아님 |
| 신규 AWS 구축 참조 설계 | 구현 | 논리 VPC/AZ/AWS 서비스 **제안**; AWS 실계정 검증/배포 없음 |
| 온프레미스 이전 목적 선택 | 구현 | 온프레미스 Inventory/As-Is·마이그레이션 평가는 **미구현**. 보고서에서 보류 명시 |
| 근거·제약/DB 전환 주의·보안/운영 검토 | 기반 구현 | 실제 운영 정책·부하·백업/복구 검증 전 |
| 비용·용량 입력 기반 비교 | 선택 구현 | 사용자가 제공한 가격·집계 부하에 한정; 전체 청구액 아님 |
| **Local AWS Inspector** | **미구현** | AWS Profile/SSO 로컬 진단은 후속 개발 |
| GitHub App 설치/온라인 SaaS | **미구현** | 서버 코드가 있어도 실제 운영 서비스로 취급하지 않음 |

## 신뢰 원칙

- **코드 관찰**: AST/구성 파일로 확인된 범위. 실행·통신을 실제 측정하지 않음.
- **사용자 입력**: 요구/정적 Inventory처럼 사용자가 직접 명시한 자료; 검증된 실계정 사실로 간주하지 않음.
- **AWS To-Be 가정**: 합리적인 참조 패턴 제안; 현재 인프라가 이와 같다는 뜻 아님.
- **미확인**: 리전별 정책, 실제 DB·트래픽, SG/IAM, RTO/RPO, SKU 단가, 데이터 이전·다운타임 등. 확인되지 않으면 통과·0원·구축 완료라고 표시하지 않음.

AI 보조 검토와 AWS 가격 API는 기본 비활성화입니다. AWS 비밀키/서버 비밀번호/원시 로그 입력을 요구하지 않으며 자동으로 AWS 자원을 변경하지 않습니다.

## 개발 우선순위

1. [#33](https://github.com/Leegiyeon/Generate-Architectures/issues/33) 간편 시작/2가지 목적 선택 — 구현·검증 여부는 해당 Issue에서 관리
2. [#34](https://github.com/Leegiyeon/Generate-Architectures/issues/34) 비기밀 온프레미스 Inventory + 근거 기반 As-Is
3. [#35](https://github.com/Leegiyeon/Generate-Architectures/issues/35) Rehost/Replatform·As-Is/To-Be 변경사항과 위험
4. [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14) 간결한 보고서·실제 시각 QA
5. [#16](https://github.com/Leegiyeon/Generate-Architectures/issues/16) 정확성 회귀/오탐 감사, [#15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 비용/용량 실증

추가 개발 [로드맵](LEAN_MIGRATION_ROADMAP.md), 상세 아키텍처 [기술 문서](ARCHITECTURE.md)를 참고합니다.
