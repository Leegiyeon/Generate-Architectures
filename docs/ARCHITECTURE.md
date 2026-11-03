# 시스템 설계·데이터 흐름 (현재 구현과 향후 목표 구분)

## 설계 목표와 경계

이 프로젝트는 **AWS Solutions Architect의 반복적인 초안 작성·검토 문서화 작업을 지원**하기 위한 자동화 도구입니다. 저장소 내용만으로 알 수 없는 업무 SLA, 데이터 지역, 보안·운영 책임, 트래픽은 **사용자에게 질문**합니다. 설계의 최종 승인권은 사용자에게 있습니다.

**기본 실행**은 저장소 정적 분석과 재현 가능한 규칙 엔진만 사용합니다. 사용자가 명시적으로 활성화하면 OpenAI 보조 검토와 제한된 AWS Price List 단가 조회를 수행할 수 있으며, Terraform plan JSON에 대한 일부 정적 정책 검사도 지원합니다. **실제 AWS 계정/운영 자원 조회, AWS 리소스 변경, Terraform/CDK 자동 배포, 실측 성능 검증은 제공하지 않습니다.** 파일 이름만 보고 보안 적합이나 월간 비용을 보장하지 않습니다.

## 컴포넌트와 입출력

| 순서 | 파일 | 입력 | 출력 | 책임 |
| --- | --- | --- | --- | --- |
| 1 | `scripts/repository_analyzer.py` | 체크아웃된 저장소 디렉터리 | 기술·API 경로·DB·인증·백그라운드 작업·IaC 단서, 확인된 파일 경로 | 안전한 구조 탐지 |
| 2 | `scripts/requirements_model.py` | 선택 요구사항 JSON, CLI 값 | 검증된 요구사항 및 부족한 질문 | 입력 값의 유효성·일관성 검사 |
| 3 | `scripts/architecture_advisor.py` | 저장소 근거 + 요구사항 | 선택된 참조 패턴, 4개 대안, 제한사항, 6원칙 체크리스트, 한국어 보고서 | 검토용 결정과 설명 |
| 4 | `scripts/render_aws_icons.py` | 서비스 목록 및 연결 관계 | `architecture.png`, `architecture.svg`, `architecture.dot` | 서비스 아이콘 시각화 |
| 5 | `scripts/recommend_architecture.py` | CLI / Action 입력 | 다양한 JSON/Markdown 및 다이어그램 | 실행 파이프라인 조율 |
| 6 | `action.yml` / `.github/workflows/...` | **수동 설계 실행**, push/PR 테스트 | 수동 실행 시에만 다운로드 가능한 Actions Artifact | 최초/선택형 설계와 자동 코드 품질 검사를 분리 |
| 7 | `app/server.py` | 유효한 GitHub App 웹훅 | 대상 저장소의 workflow_dispatch | **서버 코드만 존재** (호스팅·등록·설치 미완료) |

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

## 비용 및 IaC 정책 검토 (확장)

- `scripts/cost_estimator.py`: 사용자에게서 받은 리전/사용량/상품 조회 조건으로 보수적인 비용 시나리오를 생성합니다. `manual_quote` 출처는 공식 AWS URL과 기준일이 필요합니다. 선택적으로 인증된 Price List GetProducts를 호출하되, **단일 상품·단일 비계층 요금**인 경우에만 비용에 반영합니다. 모든 항목에 단가가 없으면 총액은 `null`입니다.
- `scripts/iac_policy_validator.py`: 사용자가 **일시적으로 생성한 Terraform plan JSON**의 `resource_changes[].change.after`를 읽어 S3 공개 접근, 관리자 포트 공개, RDS 공개·암호화 해제, IAM 광범위 허용 등의 **명시적 일부 설정**만 검사합니다. 이 분석기가 Terraform을 실행하지는 않습니다.
- 입력 원본 Terraform JSON, 자원 주소, 정책 원문 또는 암호 값은 저장하지 않습니다. `R0001` 등의 익명 자원 식별자와 규칙·권장 조치만 보고합니다.
- 비용/API는 기본 비활성화이며, 입력·실제 권한이 제공되지 않으면 `needs_input`, `not_scanned` 상태로 남습니다. `cost-estimate.json/md`, `iac-policy.json/md`는 `architecture.json`에서 파일/상태만 참조합니다.
- Terraform 계획 검사 결과의 `limited_checks_no_findings`는 **지원한 소수 규칙에서 명시적 위험을 찾지 못했다**는 의미만 갖습니다. 보안 통과를 뜻하지 않으며 `production_ready`는 항상 `false`입니다.

실제 운영의 보안/가격 검증 및 IAM 권한, 유지보수는 [COST_SECURITY_OPERATIONS.md](COST_SECURITY_OPERATIONS.md)에 기술합니다.

## 제품 단계별 기술 경계 (Issue #9)

기본 사용자 업무 흐름은 **수동 GitHub Actions 실행 → 리포지토리 사실 수집 → 누락된 사용자 요구 확인 → AWS 참조 설계 및 대안 → 근거·검증 전 보고서 → Artifact 다운로드**입니다. GitHub `push`/PR에는 기존 코드 테스트만 실행되고 전체 아키텍처 생성은 수행되지 않습니다. 외부 저장소에서 필요한 경우에만 선택형 PR 분석 예시를 설치합니다.

현 단계의 4개 참조 패턴과 서비스 아이콘은 **실구축용 VPC·Subnet·AZ 상세 토폴로지가 아닙니다**. 이를 포함한 상세 설계, 대안 선정 근거, 보안·트래픽·유지보수 청사진은 [#11](https://github.com/Leegiyeon/Generate-Architectures/issues/11)~[#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14)에서 구현합니다.

**선택형 Local AWS Inspector는 미구현**이며, 추후 AWS CLI Profile/SSO 기반 읽기 전용 로컬 진단으로 분리합니다. Access Key 직접 입력 웹페이지, 중앙 계정 비밀키 저장, 실제 AWS 리소스 생성/수정/삭제는 제품 범위에서 제외합니다. [전체 사용자 여정 문서](PRODUCT.md)를 단일 제품 정의의 근거로 사용합니다.

## 정적 근거 계약 및 요구사항 Gap Analyzer (Issue #10)

`scripts/evidence_contract.py`는 API·모델·직접 호출(소스 AST)과 설정파일 탐지 결과를 구분하고, **관측 시점·근거·불확실성**을 가진 데이터로 재구성합니다.

| 필드 | 의미 | 해석 시 주의 |
| --- | --- | --- |
| `observations` | F0001… 정적 API/모델/호출·설정 파일을 관찰 | 파일 경로/행은 실제 런타임 또는 운영 계정의 검증 근거가 아님 |
| `configuration_inferences` | I0001… DB·인증·Docker 등 설정 기반 신호 | 추정 단서이며 실행 여부는 확인되지 않음 |
| `user_requirements` | R0001… 사용자가 명시한 요구사항 | 원본 입력 파일/CLI에 존재하는 키만 기록 |
| `system_defaults` | environment=dev, workload=auto 등 | 내부 기본값으로, 사용자의 승인/입력과 다름 |
| `assumptions` | A0001… AWS 참조 제안의 가정 | 클라우드 운영 사실이 아님 |
| `unknowns` | U0001… 요청량·운영·보안·RTO/RPO 등 질문 | 값이 없으면 미확인으로 두고 임의 수치를 채우지 않음 |

`analyzed_at_utc`와 `coverage`는 파서 오류, 파일/그래프 분석 상한, 미지원 영역을 포함합니다. 직접 관찰은 `static_observed`, 설정 감지는 `configuration_indicator`처럼 분류하고 **근거 없는 백분율 confidence는 만들지 않습니다**.

`parse_requirements(return_provenance=True)`는 기존 호출자의 사전 호환성을 유지하면서 사용자 명시 입력 키 목록을 반환합니다. 사용자 확인 완료된 `rendering_mode` 및 `document_database_strategy`도 보존하여 이후 동일한 질문을 다시 하지 않습니다. `run()`은 공통 계약으로 질문을 결정하며, 이미 코드에서 탐지된 인증·DB 단서나 이미 입력된 값을 다시 요구하지 않습니다. 다만 구성 요소 발견은 실제 구현·보안 정책 적합성 검증이 아닙니다.

수동 AI 리뷰에서는 데이터 보호를 위해 source path, 함수 이름, 원본 코드가 아닌 정적 기술 신호·AST 개수·**명시적** 요구사항만 전송하며 시스템 기본값을 사용자 입력으로 표시하지 않습니다.

생성 파일: `evidence-contract.json`, `evidence-report.md`, `requirements-gaps.json`. 이 자료는 향후 [Issue #11](https://github.com/Leegiyeon/Generate-Architectures/issues/11)의 상세 To-Be 설계에 필요한 출처 계약이며, 현재 상세 AWS 네트워크가 완성된 것으로 해석하지 않습니다.

## AWS To-Be 논리 토폴로지 (Issue #11 기반 구현)

`scripts/aws_topology.py`는 기존 간단 참조 설계와 사용자 요구·근거 계약을 조합하여 `aws-topology.json`을 생성합니다. `scripts/render_aws_topology.py`는 별도 `aws-topology.svg/png/dot`을 렌더링합니다. 포함된 AWS 영역, VPC, 두 논리 AZ의 Public/Private/DB Subnet, ALB/ECS/RDS 등의 계층 및 연결은 **참조 설계 제안**이며 배포 상태가 아닙니다. 정적/서버리스 패턴에서 불필요한 VPC는 자동 생성하지 않습니다.

코드 기반 As-Is Application Graph, AWS 아이콘 서비스 참조도, To-Be 상세 논리 토폴로지는 각각 독립된 산출물입니다. 상세 토폴로지는 모든 노드/간선에 `proposed_not_deployed` / `proposed_not_verified` 상태를 유지합니다. 구축 전 NAT 또는 PrivateLink, SG/IAM, Route Table, 실제 AZ/CIDR, ACM/TLS, RDS DB subnet group 및 비용을 별도 확인해야 합니다.

상세 문서: [TOPOLOGY.md](TOPOLOGY.md). 실제 VPC/서브넷/네트워크 보안 구현, 트래픽 및 장애 복구 정책은 다음 단계(#11~#13)에서 고도화합니다.

## 네트워크 정책·AWS 아이콘 통합 설계

`scripts/topology_network_policy.py`: `aws-topology.json`의 모든 노드/간선에 AWS 설계 규칙 ID를 부여하고 사용자가 명시한 ALB 공개/내부 범위, NAT 또는 VPC Endpoint, 보안그룹/라우트 의도를 분리해 기록합니다. 포트·CIDR·라우트·자원 ID를 입력하지 않은 경우 실제 배포 값으로 채우지 않습니다. VPC Endpoint만으로 일반 인터넷 API를 호출하는 조건은 충돌로 표시합니다.

`scripts/render_aws_topology.py`: Diagrams 패키지에 포함된 서비스 PNG 아이콘을 논리 AWS Cloud/VPC/AZ/Subnet 클러스터 안에 배치하고, SVG 내에 PNG를 인라인 저장합니다. 미지원 네트워크 구성은 텍스트로 표시합니다. 정확한 실제 정책의 검증은 수행하지 않습니다.

`network-policy.md`에 보안그룹 접근 의도, Route Table 계획 미완성 상태, AWS 공식 설계 근거와 검토 항목을 요약합니다. `aws-topology.json`의 `design_rule_ids`는 근거를 추적하는 설계 규칙이지 컴플라이언스 통과 증명이 아닙니다. 다음은 서비스 선택 근거 개선(#12)과 운영/스케일링 설계(#13)입니다.

## 서비스별 AWS Architecture Decision Matrix (Issue #12 1차)

`scripts/architecture_decision_engine.py`는 현재의 참조 패턴 선택을 **유지한 채** Static/S3+CloudFront, Lambda+API Gateway, ECS Fargate+ALB, EC2+ALB 및 Mobile API를 비교합니다. `max_job_duration_seconds`, `requires_host_control`, DB 사용 단서, SSR 유무, 트래픽/운영 선호 등에서 **현재 템플릿에 해당하는 충돌**을 찾습니다. EC2는 현재 다이어그램에 없는 검토 후보이고, 비용/성능 측정 결과가 없어 정량 점수·자동 순위가 없습니다.

출력 `architecture-decision-matrix.json/md`에는 후보별 `blockers`, `review_required`, `rationale`, `tradeoffs` 및 미검증 상태가 포함됩니다. 선택된 현재 참조 템플릿에 명시적인 블로커가 있으면 `validation.json`에도 `DEC-001`을 추가하고 자동 채택을 차단합니다. AI 보조 의견은 패턴 변경 권한이 없으며, 사람의 별도 ADR 승인이 필요합니다. 자세한 설명: [DECISIONS.md](DECISIONS.md).

## 데이터 접근·미승인 결정 기록의 분리

`scripts/data_access_decision.py`: SQL/문서/키 기반 접근 사용자의 명시적 선택과 정적 DB 패키지 신호를 구별해 RDS, DynamoDB, 문서형 기존 DB, DocumentDB의 **이전 위험·호환성 조건**을 제시합니다. 마이그레이션을 자동 승인하거나 운영 데이터를 전송하지 않습니다.

`scripts/architecture_decision_engine.py`의 `build_decision_record`는 명시적인 입력과 시스템 기본값을 분리하고, 선택 패턴·제외 이유·ADR 승인 대기 상태를 JSON/Markdown으로 기록합니다. 저장소의 실제 성능·비용 및 AWS 운영 리소스를 검증하지 않았으므로 `approved=false`가 기본입니다.

`scripts/ec2_alternative.py`: Fargate 네트워크 후보에서 VPC/AZ/ALB/DB 경계만 참고하여 EC2 ASG 기반 **독립 제안**을 만들고, 별도 아이콘 SVG/PNG 및 검토 보고서를 제공합니다. Fargate용 Private egress를 EC2에 그대로 적용하지 않습니다.

## Security / Scaling / Operations Designer (Issue #13)

scripts/operations_designer.py는 AWS To-Be 토폴로지의 실제 노드/간선과 network_controls에 존재하는 서비스만 연결하여 IAM/Secrets/SG·ECS/Lambda Scaling 후보·CloudWatch 알람·RDS 백업 및 Well-Architected 6개 원칙의 검토 항목을 구조화합니다.

- **무결성:** ALB→ECS 실제 설계 간선과 SG 통제 의도가 맞지 않으면 오류를 발생시킵니다. 해당 리소스가 없는 Static/Serverless에 ECS/RDS 정책을 넣지 않습니다.
- **출처:** RTO/RPO/피크 RPS/지연 시간/가용성 목표는 사용자 입력과 시스템 기본값을 분리합니다. 미입력값 또는 계정 실측값은 작성하지 않습니다.
- **보안:** 공개/내부 ALB의 차이를 SG/운영 검토로 반영하고 Endpoint-only 외부 인터넷 API 충돌을 표시합니다.
- **성능:** ECS 타깃 CPU/Memory/ALB 요청, Lambda ConcurrentExecutions 등 후보를 제공하되 실제 임계값, 용량, 쿼터, SLA 달성 상태는 null/검증 전으로 유지합니다.
- **결과:** security-operations.json/md에 제안된 통제, CloudWatch 알람 후보, 복구·운영 확인 질문과 6개 Well-Architected 검토 상태를 기록합니다.

전체 세부 설명은 [OPERATIONS.md](OPERATIONS.md)를 참고하세요.

## 사용자용 결과물 묶음 (Issue #14)

scripts/report_bundle.py는 모든 JSON·Markdown·AWS SVG/PNG가 생성된 **이후에** 단일 오프라인 START-HERE.html과 START-HERE.md, deliverables/의 4개 범주 결과물, artifact-index.json(상대경로·SHA256)을 생성합니다. 기존 JSON, DOT, 코드 AST·IaC·AI 검토 산출물은 하위 호환을 위해 그대로 유지합니다. HTML에 원격 스크립트·이미지/CSS를 추가하지 않고 CSP 및 문자열 이스케이프로 브라우저 실행 위험을 제한합니다. SVG는 기존 AWS 아이콘 내장 파일을 data URI로 추가 내장하여 오프라인으로 확인할 수 있게 했습니다.

원본 선택 패턴/ADR, 정적 Validator 게이트/토폴로지 상태/운영 CloudWatch 노드, 완전하지 않은 비용 모델의 월 총액 제시가 서로 모순되면 사용자 보고서 생성을 실패시킵니다. 보고서에서 실제 AWS 계정/보안/용량/복원 실증을 수행했다고 표시하지 않습니다. 비용의 완결성은 입력된 상품/사용량 범위로 한정됩니다.

사용자 가이드: [REPORTING.md](REPORTING.md).

## AWS 비용 시나리오 v2 기반 구현 (Issue #15)

`scripts/cost_scenarios.py`는 사용자 입력의 월 최소/기준/피크 수량을 엄격 검증하고, 기존 `scripts/cost_estimator.py`의 AWS 공식 출처·리전·단가 보안 정책을 재사용합니다. 동일한 AWS Price List SKU/단가는 3개 시나리오에서 1회만 조회하도록 구성하며 실시간 조회는 기본 비활성화합니다.

`correlate_topology_costs`는 현재 AWS To-Be 노드와 ALB/ECS/RDS/Lambda/NAT/Endpoint/전송·로그/백업 등의 비용 **분류 태그**가 존재하는지만 검사합니다. 리전 불일치 및 누락 분류를 표시하고, `complete_for_entire_architecture=false`를 유지합니다. 상품/SKU/추가 요금·무료 한도·할인/세금 등의 전체 비용 검증은 아직 수행하지 않습니다.

v1 비용 JSON은 호환 유지, `cost-estimate.json/md`와 `deliverables/04-cost-capacity.md`, `START-HERE.html`에 v2 시나리오 비교가 추가됩니다. 상세 입력 및 한계: [COST_SCENARIOS.md](COST_SCENARIOS.md).
