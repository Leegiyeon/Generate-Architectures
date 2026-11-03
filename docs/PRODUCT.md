# Generate-Architectures — 제품 목적 및 사용자 업무 흐름

> **제품 정의:** GitHub 저장소와 사용자가 명시한 요구사항으로 AWS **권장 설계 초안과 선정 근거**를 제공하는 설계 지원 도구입니다. AWS 환경의 운영·자동 배포 도구가 아닙니다.
>
> **현 단계:** 정적 코드 분석과 4종 참조 패턴, AWS 아이콘 다이어그램, 근거·리스크·ADR 초안 제공. 상세 VPC/Subnet/AZ의 **논리 제안 기반은 구현 중**이고 프로젝트별 트래픽/운영 설계는 [Issue #11](https://github.com/Leegiyeon/Generate-Architectures/issues/11)~[#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14)에서 구현할 목표입니다.

## 1. 사용자에게 제공하는 두 가지 기능

| 제품 기능 | 실행 위치 | 사용자 가치 | 상태 |
| --- | --- | --- | --- |
| **Architecture Designer (핵심)** | GitHub Actions 또는 CLI | 코드 구조와 요구사항을 분석하여 AWS 설계 초안·추천 이유·대안 비교·주의사항을 다운로드 | **기반 기능 동작, 상세 설계는 구현 중** |
| **AWS Account Inspector (선택)** | **사용자 로컬 PC** | AWS CLI Profile/SSO의 읽기 전용 권한으로 실제 계정 구조를 조회하고 권장 설계와 차이를 보고 | **아직 미구현**, [#17](https://github.com/Leegiyeon/Generate-Architectures/issues/17) 및 [#18](https://github.com/Leegiyeon/Generate-Architectures/issues/18) |

기존 **GitHub App 서버 코드**는 설치·호스팅되지 않은 웹훅 연동용 기초 코드입니다. 사용자 로그인, 프로젝트 관리 웹 UI, 운영 중인 온라인 SaaS는 현재 제공하지 않습니다. Local Inspector의 AWS 인증 입력 UI에도 Access Key/Secret Key 직접 입력란을 만들지 않습니다.

## 2. 핵심 사용자 여정 — 최초 1회 분석 및 필요시 재분석

```text
사용자: 저장소에서 Actions → 'AWS 아키텍처 검토 자동화' → Run workflow
  ① 저장소 파일·패키지·API/함수 구조 정적 분석
       → evidence-contract.json에 관찰/설정 단서/명시 입력/기본값/가정/미확인 구분
  ② 요구사항 파일이 있으면 적용. 없으면 미확인 항목을 질문으로 출력
       → 추가 입력 후 수동 재분석 가능
  ③ Static / Serverless / Container / Mobile 참조 패턴 검토
       → 지금은 4종 후보 비교. 2~3개 세부 배포 대안 설계는 #11~#12
  ④ 규칙 기반 제약 검사 + (명시 동의 시) 보조 AI 검토
       → 실제 AWS 리소스·계정은 조회하지 않음
  ⑤ AWS 서비스 아이콘 다이어그램 + 근거/대안/리스크 보고서 생성
       → 상세 네트워크/보안·확장성·운영 전략은 #11~#14에서 보강
  ⑥ Actions Artifact에서 결과 다운로드
       → 사용자가 직접 검토/승인, AWS 배포 작업 없음
```

기본 실행은 **한 번 요청해서 한 번 설계**하는 방식입니다. 중요한 요구사항이 바뀌면 요구사항 JSON을 수정한 뒤 사용자가 다시 실행합니다. GitHub의 `push`·`pull_request` 이벤트에 대한 **자동 코드 테스트는 계속 수행**하지만, 전체 아키텍처 생성과 Artifact 생성은 **수동 `workflow_dispatch` 이벤트에서만** 실행합니다.

다른 GitHub 저장소에 적용할 때도 [기본 예시](../examples/aws-architecture.yml)는 수동 실행입니다. PR마다 분석이 반드시 필요한 팀에 한해 [선택형 PR 분석 예시](../examples/aws-architecture-pr-optional.yml)를 설치할 수 있습니다. GitHub App의 웹훅 연동은 별도 설치 후에만 실행되며 현재의 기본 흐름이 아닙니다.

## 3. 입력: 사용자는 무엇을 준비해야 하나?

| 입력 | 필수 여부 | 실제 처리 |
| --- | --- | --- |
| GitHub 저장소 | 필수 | GitHub Actions가 해당 저장소를 체크아웃하여 정적 분석 |
| `.architecture/requirements.json` | **선택** | 서비스 환경, 데이터 분류, 리전, 월 요청수, 예산, 가용성, RTO/RPO 등을 지정 |
| 평균/피크 RPS, 업무상 중요도 | 상세 설계 목표에 필요 | **요구사항 JSON에서 입력 가능** (평균·피크 RPS, 동시 연결, 지연 목표, 운영 우선순위). 별도 UI는 아직 없음 |
| `enable_ai`, `OPENAI_API_KEY` | 선택 | 기본 꺼짐. 명시된 경우에만 요약된 비기밀 근거 외부 전송 |
| 비용 JSON / AWS Price List API | 선택 | 미입력은 `needs_input`. 요율 불확실 시 전체 금액 미산정 |
| Terraform plan JSON | **선택, 로컬에서만 권장** | 일부 정책의 정적 확인. 원문은 비밀정보 포함 가능하므로 Git 추적 금지 |
| AWS 계정 ID/Access Key/Secret Key | **요구하지 않음** | Designer는 AWS 로그인·실운영 조회 없이 실행 |

사용자가 입력하지 않았고 코드에서도 확인할 수 없는 내용을 사실로 주장하지 않습니다. 사용자에게 반복 질문하지 않도록 코드로 확인된 단서와 명시적인 입력을 분리하여 evidence-contract.json에 기록합니다. 단, 실제 트래픽과 운영 배포 설정은 검증하지 않습니다.

## 4. 출력: 사용자가 무엇을 얻는가?

**현재 제공**

- `architecture.svg/png` — AWS **참조 설계의 서비스 구성도**. VPC/서브넷/AZ 단위의 실제 구축·운영 검증 결과 아님. 추가 `aws-topology.svg/png`는 상징적인 AZ를 포함한 **네트워크 논리 제안**.
- `recommendation.md` — 선택 이유·대안 비교·보안/가용성 확인 사항을 포함한 한국어 검토 보고서.
- `decision-record.md` — 선택된 참조 패턴과 근거·미확인 문제를 담은 **미승인 ADR 초안**.
- `application-graph.svg/png/json` — 정적 분석으로 확인되는 일부 코드 구조·호출 관계.
- `validation.md/json` — 참조 패턴과 입력 간 정적 충돌 및 미측정 항목. 합격/인증 결과 아님.
- `evidence-contract.json`, `evidence-report.md`, `requirements-gaps.json` — 관측 사실/설정 단서/사용자 명시입력/기본값/가정/미확인 조건.
- `cost-estimate.md/json`, `iac-policy.md/json`, `ai-review.md/json` — 기능이 비활성화되었으면 **미실행/미산정 표시**.

**목표 산출물 ([#11](https://github.com/Leegiyeon/Generate-Architectures/issues/11)~[#15](https://github.com/Leegiyeon/Generate-Architectures/issues/15))**

1. 프로젝트 조건에 맞는 상세 AWS To-Be 설계도(VPC·Subnet·AZ·서비스 연결·가정 명시) — **논리 토폴로지 기반 구현, 실환경·보안/라우팅 검증은 미완료**.
2. 서비스별 **선정/제외 근거와 2~3개 배포 대안** 비교.
3. Security & Operations 설계(최소 권한, 네트워크 통신 경계, 오토스케일, 모니터링, 백업·복구).
4. Cost & Capacity 비교(리전·사용량·가격 기준일 표시, 미산정 항목 구분).

## 5. 책임·권한 및 안전 경계

- 도구가 **AWS 리소스를 생성·변경·삭제하거나 자동 배포하지 않습니다**. 실제 실행을 사용자가 별도로 결정합니다.
- 기본 GitHub Workflow는 `contents:read`만으로 분석하며, PR/push에서는 **테스트만** 수행합니다.
- 외부 AI 호출과 AWS 가격 API 조회는 **수동 실행 및 명시적 활성화**가 필요합니다. 호출 비용과 서비스 제공자의 데이터 정책을 확인하세요.
- `production_ready`, AWS 보안·가용성·비용의 합격 판정은 도구가 제공하지 않습니다. 증거가 부족하면 미검증으로 남깁니다.
- Local AWS Inspector(향후 기능)는 **기존 AWS CLI Profile 또는 IAM Identity Center 기반 임시 인증**을 이용하고, 읽기 전용 조회와 로컬 결과 보관을 기본으로 설계합니다. 중앙 서비스에 계정 비밀키를 수집·저장하지 않습니다.
- GitHub Actions Artifact는 저장소에 접근 가능한 사람과 플랫폼 권한 정책에 의해 열람 가능할 수 있으므로, 보고서의 코드 경로·아키텍처 단서도 **기밀 수준에 따라 보관/삭제**해야 합니다.

## 6. 제품 외부에 두는 것

현재 범위에 없는 기능은 AWS 자동 배포, Terraform apply, AWS 자원 변경, AWS 계정 자격증명의 중앙 수집·보관, 24시간 인프라 모니터링/장애 자동 복구, SLA 및 보안 인증 보증, GitHub App의 자동 설치·호스팅입니다.

## 7. 개발 우선순위 및 검수 기준

- [#9](https://github.com/Leegiyeon/Generate-Architectures/issues/9): 사용자 여정/제품 경계/수동 중심 실행 정책 (**본 문서**)
- [#10](https://github.com/Leegiyeon/Generate-Architectures/issues/10): 정적 분석 근거와 미확인 요구사항의 공통 계약 (**기반 구현 완료**)
- [#11](https://github.com/Leegiyeon/Generate-Architectures/issues/11): 상세 AWS 토폴로지
- [#12](https://github.com/Leegiyeon/Generate-Architectures/issues/12): 선택 이유·대안 엔진
- [#13](https://github.com/Leegiyeon/Generate-Architectures/issues/13): 보안·운영·확장 설계
- [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14): 결과물 UX 통합

최초 분석 후 보고서에서 **입력 → 출력 → 확인되지 않은 정보 → 다시 실행하는 방법**을 사용자가 설명할 수 있어야 합니다. 제품 기능의 미구현 사항은 완료로 표시하지 않습니다.
