# 시스템 설계·데이터 흐름 (2026-11-02 기준)

## 설계 목표와 경계

이 프로젝트는 **AWS Solutions Architect의 반복적인 초안 작성·검토 문서화 작업을 지원**하기 위한 자동화 도구입니다. 저장소 내용만으로 알 수 없는 업무 SLA, 데이터 지역, 보안·운영 책임, 트래픽은 **사용자에게 질문**합니다. 설계의 최종 승인권은 사용자에게 있습니다.

현재 구현은 **오프라인 결정적 규칙 엔진**입니다. LLM 서비스 호출, AWS 계정 조회, AWS 가격표 조회, Terraform/CDK 수정, 실제 배포, 성능 측정 기능은 없습니다. 파일 이름만 보고 '보안 적합' 또는 '월 XX달러 보장'처럼 말하지 않습니다.

## 컴포넌트와 입출력

| 순서 | 파일 | 입력 | 출력 | 책임 |
| --- | --- | --- | --- | --- |
| 1 | `scripts/repository_analyzer.py` | 체크아웃된 저장소 디렉터리 | 기술·API 경로·DB·인증·백그라운드 작업·IaC 단서, 확인된 파일 경로 | 안전한 구조 탐지 |
| 2 | `scripts/requirements_model.py` | 선택 요구사항 JSON, CLI 값 | 검증된 요구사항 및 부족한 질문 | 입력 값의 유효성·일관성 검사 |
| 3 | `scripts/architecture_advisor.py` | 저장소 근거 + 요구사항 | 선택된 참조 패턴, 4개 대안, 제한사항, 6원칙 체크리스트, 한국어 보고서 | 검토용 결정과 설명 |
| 4 | `scripts/render_aws_icons.py` | 서비스 목록 및 연결 관계 | `architecture.png`, `architecture.svg`, `architecture.dot` | 서비스 아이콘 시각화 |
| 5 | `scripts/recommend_architecture.py` | CLI / Action 입력 | JSON 3종 및 Markdown, 다이어그램 | 실행 파이프라인 조율 |
| 6 | `action.yml` / `.github/workflows/...` | GitHub 이벤트 | 다운로드 가능한 Actions Artifact, PR 댓글 | 자동 실행 및 결과 전달 |
| 7 | `app/server.py` | 유효한 GitHub App 웹훅 | 대상 저장소의 workflow_dispatch | GitHub App 외부 이벤트 연결 (호스팅·등록 별도) |

### 실제 파일을 읽는 방식

- 디렉터리·파일 이름 최대 5,000개를 탐색하며 `.git`, 의존성/빌드 폴더 및 심볼릭 링크는 제외합니다.
- `package.json`의 의존성 이름을 확인합니다. `next.config.*` 중 크기가 제한된 파일에서 명시적 `output: 'export'` 여부를 확인합니다.
- `.env` 등 비밀 설정 파일의 내용은 읽지 않습니다. 모든 분석은 GitHub Runner 내부에서 실행하고 외부 LLM으로 소스 내용을 보내지 않습니다.
- 발견되지 않았다는 것은 해당 기능이 **없다는 증거가 아닙니다**. 특히 API 서버, SSR, DB·인증·운영설정은 수동 확인이 필요합니다.

## 설계 대안 결정 기준

1. `workload`가 auto라면 모바일 기술 단서 → 웹 기술 단서 → 백엔드 순서로 분류합니다.
2. Next.js에서 **명시적으로 정적 export를 확인하지 못한 경우** SSR 및 서버 액션 가능성을 남기고 컨테이너 패턴을 초기 비교 대상으로 선택합니다.
3. Vite 등 정적 자산 후보는 서버/API 단서나 관계형 DB 요구가 없을 때만 정적 아키텍처를 검토합니다.
4. 관계형 DB 단서나 `requires_relational_database: true`가 있으면 DynamoDB를 전제로 한 서버리스 패턴은 기본 비교에서 배제합니다. 관계형 DB 사용 여부와 RDS 엔진은 **별도 확인**합니다.
5. 사용자가 요구사항에서 배포 선호를 입력했더라도 근거상 충돌하면 자동 선택하지 않고 이유를 경고로 남깁니다.
6. 최종 추천은 **참조 패턴**이지 실제 배포 적합성 검증 결과가 아닙니다.

### 리소스 배치 다이어그램의 의미

아이콘은 AWS 서비스의 **후보**를 보여줍니다. 실선은 요청·데이터 흐름의 **참조 연결 관계**, 금색 점선은 보안 연계, 회색 점선은 관측 정보를 의미합니다. 실제 VPC·AZ·Subnet·Security Group·라우팅 테이블 또는 사내 전용망 구성은 검사되지 않습니다. 설계도를 인프라 구축 지시서로 바로 사용하지 마세요.

## Well-Architected 검토 모델

6개 영역은 모두 초기 상태 **검증 전**입니다: 운영 우수성, 보안, 안정성, 성능 효율성, 비용 최적화, 지속 가능성. 향후 AWS 계정·IaC 정적 정책검사·부하 및 장애 테스트 등 확인 가능한 검증 근거가 생기기 전까지 **자동 합격/실패 점수**를 표시하지 않습니다.

## 근거 추적 설계

- `repository-analysis.json`: 관찰된 설정파일 및 단서만 저장.
- `requirements-used.json`: 사용자의 명시적 비기밀 요구사항.
- `architecture.json`: 선택 이유, 각 대안 검토 가능 여부, 운영 제약과 미확인 질문.
- `recommendation.md`: 검토자가 승인 전 읽을 수 있는 한글 요약.

**불변 규칙:** 관찰 사실(fact) / 사용자 입력(requirement) / 설계 추정(proposal) / 검증 결과(validation)을 서로 혼합하지 않습니다.

## 향후 개선 시 지킬 원칙

실제 코드 간 호출 연결은 AST/언어별 분석기로 파일·함수 단위 근거를 추출한 후 검증합니다. LLM은 후보 생성과 사용자 질문 정리에만 활용하고, AWS 비용·보안은 공식 가격 데이터와 정책 엔진/실제 테스트를 통해 판정해야 합니다. 외부 API 전송 전에는 비밀/민감정보 제거와 명시적인 사용자 동의가 필요합니다.

## P0 애플리케이션 AST 그래프 (구현)

`application_graph.py`는 Python 소스를 표준 라이브러리 `ast`로 분석하고, `scripts/js_analyzer/analyze.cjs`는 Babel의 TypeScript/JavaScript AST를 사용합니다. Babel은 **파싱만 하며** 대상 저장소 코드를 실행하지 않습니다.

기본 노드: `module`, `function`, `route`, `model`. 연결: `defines`(정의), `imports`(로컬 참조), `handles`(라우트 핸들러), `calls`(정적 심볼로 확인한 직접 호출). 모든 노드와 간선은 근거 경로 및 행 번호를 가지며, 식별자는 파일 상대 경로를 포함해 중복을 방지합니다.

`application-graph.json`을 원본 데이터로 사용하고 `render_application_graph.py`가 별도 SVG/PNG/DOT을 만듭니다. 기존 AWS 참조 설계(`architecture.json` 및 서비스 아이콘 그림)는 **제안**이고, 이 애플리케이션 그래프는 **정적 분석 근거**입니다.

일부 파일을 분석하지 못하면 `errors`에 이유를 기록하고, 소스 파일과 결과 노드/간선의 최대 수를 제한합니다. JS/TS의 동적 import, 런타임 DI, path alias, 복잡한 ORM 관계, Go·Java 함수 호출 추적은 아직 지원하지 않습니다. AST에서 찾은 API가 실제 운영 라우팅/인가 정책을 증명하는 것은 아닙니다.

개선된 파이프라인: 저장소 메타데이터 수집 → **코드 AST 분석** → 검증된 API 단서를 설계 판단에 반영 → 한국어 설계 검토 → AWS 후보 다이어그램 + 별도의 실제 코드 구조 다이어그램 → Artifact.

## AI 설계 검토 Agent — 선택적 판단 분기

`scripts/ai_architecture_agent.py`는 기존 규칙 기반 `architecture_advisor.py`의 **후단**에 연결합니다. 기본적으로 외부 전송은 발생하지 않으며, 수동 실행에서 `enable_ai`를 명시하고 `OPENAI_API_KEY`가 있을 때만 모델을 호출합니다.

```text
소스 파일 + 요구사항
  → Repository Analyzer / AST Graph (로컬, 실행 없음)
  → Rule-Based Architecture Advisor (기존 설계도 확정 아님)
  → [사용자 동의 및 API 키 존재 시] 최소 정보 집계
  → Evidence ID 부여 (E001, E002 ...)
  → OpenAI Responses API / 구조화된 JSON / store=false
  → 로컬 검증: 참조 ID 실재 여부, 대안 적용 가능성, 문자열 및 배열 상한
  → ai-review.json + ai-review.md (검증 전 보조 의견)
  └─ 기존 architecture.json의 선택 및 SVG/PNG는 변경하지 않음
```

### 데이터 계약

- **관찰(observed):** 정적 분석에서 감지한 참인 기술 신호와 AST 노드 개수. 없음/미탐지는 부재 증명이 아닙니다.
- **요구(requirement):** 등록된 데이터 분류·워크로드·SLO/RTO/RPO/예산 등의 검증된 입력값.
- **제안(proposal):** LLM의 대안 ID·근거 ID·위험 설명·추가 질문. 참고 의견이며 **검증 전**입니다.
- **검증(validation):** 앱은 출력 구조/ID/허용 대안만 검증합니다. AWS 리소스/비용/정책 통과 여부는 검증하지 않습니다.

모델 프롬프트에는 저장소 이름, 소스 내용, 파일·함수명, URL, 원본 AST 노드·호출 그래프를 포함하지 않습니다. 외부 전송은 집계 수치·허용된 요구사항 필드 및 근거 ID로 제한됩니다. 사용자 제어 Secrets는 출력 로그/Artifact에 넣지 않습니다. 인증 오류/타임아웃 시 API 응답 본문은 저장하지 않습니다.

요청에는 `store: false`를 지정하며, 이것이 모든 데이터 처리·보존 정책을 없애는 의미는 아닙니다. 사용자의 조직 보안 정책을 우선 적용해야 합니다.

이 엔진은 GitHub 자동 PR 이벤트에서 호출하지 않습니다. Actions 수동 실행만 허용하며, 타 저장소 재사용 시 이용자가 명시적으로 전달해야 합니다. AI 모델은 아키텍처를 수정·배포할 권한이 없습니다.

## Architecture Validator v1 — 설계 결정에 대한 정적 제약 검사

분석/설계/AI 보조 검토 뒤, 배포나 AWS 계정 변경 없이 `scripts/architecture_validator.py`가 정적 제약 검사를 실행합니다.

```text
코드 분석의 명시적 근거 + 사용자 JSON 요구사항
             ↓
규칙 기반 AWS 참조 패턴 선택 + (옵션) AI 보조 검토
             ↓
Architecture Validator (AI 응답으로 룰을 변경하지 않음)
  ├── ARC-* 다이어그램 노드/간선과 템플릿 정합성 검사
  ├── REQ-* 명시 요구사항 충돌 검사
  ├── PAT-* 설계 패턴과 API/DB 구조 간의 명시적 충돌
  ├── EVD-* AST 파일 누락/오류에 대한 불확실성 기록
  └── SEC/REL/OPS/PERF/COST-* 실제 검증이 필요한 조건
             ↓
validation.json / validation.md / decision-record.md
             ↓
사용자 최종 검토 및 승인 (자동 승인·실제 배포 없음)
```

모든 Finding에는 `rule_id`, `pillar`, `severity`, `title`, `detail`, `evidence`, `recommended_action`이 들어갑니다. 근거는 `requirements.requires_...`, `repository.signals...`, `architecture.nodes` 등의 **기존 구조 필드**를 참조합니다. 실제 AWS 리소스가 점검되었다는 의미로 쓰지 않습니다.

**결과 계약:** `decision_gate=blocked`는 이 참조안의 **자동 적용 제한**이고 `decision_gate=review_required`는 추가 증거 부족입니다. 두 상태 모두 `production_ready=false`, `aws_account_checked=false`, `cost_estimated=false`, `security_compliance_verified=false`, `performance_tested=false`입니다. Well-Architected 여섯 원칙은 모두 `검증 전`으로 남습니다.

검사 자체가 선택된 AWS 서비스를 추가·삭제하거나 AI가 제안한 대안으로 전환하는 동작은 없습니다. 모델이 위험을 찾아도 독립 정책/실측 확인 없이 통과시키지 않습니다. ADR은 확정사항이 아닌 사람이 검토할 수 있는 결정 기록의 **초안**입니다.

향후 단계에서는 실제 Terraform/CDK/CloudFormation 파일에 대한 읽기 전용 정책 검사 결과를 별도 provenance 필드와 함께 수집해야 하며, 이후 비용/보안/신뢰성 검사에서 미수행과 위반을 분리해야 합니다.
