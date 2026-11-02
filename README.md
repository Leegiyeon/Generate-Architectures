# Generate-Architectures — GitHub 중심 AWS 아키텍처 설계 지원

GitHub 저장소의 **확인 가능한 근거**와 **사용자가 직접 제공하는 요구사항**을 바탕으로, AWS 아키텍처 대안을 비교하고 서비스 아이콘이 포함된 다이어그램 및 한국어 검토 보고서를 생성합니다.

> **현재 단계: SAA 업무 자동화의 1~2단계 기반 구현.** 실제 AWS 리소스 조회, 검증된 LLM 자율 설계 승인, 상세 비용 산정, 보안 정책 검증, Terraform/CDK 생성 또는 인프라 배포는 제공하지 않습니다. 출력물은 전문가 검토가 필요한 **참조 설계 초안**입니다.

## 1. 실제 구현 기능

| 기능 | 현재 동작 | 한계 |
| --- | --- | --- |
| 저장소 구조 분석 | Node/Next.js/Vite/Python/Java/Go/Docker/Expo 등 설정 파일 탐지 | 함수별 호출·데이터 흐름 전체를 파악하지는 못함 |
| 근거 수집 | API 경로, 관계형 DB 관련 파일/패키지, 인증·작업 큐·IaC 단서 수집 | 파일 경로와 제한된 설정 파일에서만 추출 |
| 요구사항 분석 | 워크로드, 배포 선호, 예산, 리전, 가용성, RTO/RPO, 데이터 분류 입력 검증 | 입력하지 않은 값은 추정하거나 확정하지 않음 |
| 설계 비교 | Static / Serverless / Container / Mobile 참조 패턴 비교 | 실제 AWS 서비스 구성의 적합성 보장 불가 |
| 안전한 판단 | Next.js SSR 미확인 시 정적 호스팅으로 단정하지 않음; 관계형 DB 요구와 패턴 충돌 시 경고 | 실제 실행·성능 테스트 없이 결론 확정 불가 |
| Well-Architected | 6개 원칙의 **검증 전 체크리스트**와 추가 질문 출력 | 검증을 통과했다고 표시하지 않음 |
| 다이어그램 | Diagrams의 AWS 서비스 아이콘, PNG/SVG/DOT 생성 | VPC/Subnet/AZ는 실제 구성 근거가 없어 자동 생성하지 않음 |
| 자동화 | GitHub Actions, PR 링크, 재사용 Action, GitHub App 서버 코드 | GitHub App 등록/배포/설치 절차는 사용자 환경에서 별도 진행 |

## 2. 전체 실행 흐름

```text
GitHub PR / Actions 수동 실행
  → 대상 저장소 체크아웃 (읽기 전용)
  → 설정/경로 단서 수집 (repository_analyzer.py)
  → 비기밀 요구사항 JSON 검증 (requirements_model.py)
  → 서비스 구성 대안 비교 및 미확인 항목 정리 (architecture_advisor.py)
  → 한국어 Markdown + 근거 JSON + AWS 서비스 아이콘 PNG/SVG 생성
  → GitHub Actions Artifact 보관 / PR 결과 링크
  → 사람의 설계 검토 및 승인 (AWS 자동 배포 없음)
```

## 3. 가장 빠른 사용법

1. GitHub의 **Actions → AWS 아키텍처 검토 자동화 → Run workflow**에서 직접 실행합니다.
2. 완료된 실행의 **Artifacts → aws-architecture-recommendation**에서 결과 ZIP을 다운로드합니다.
3. `recommendation.md`에서 근거·대안·위험·추가 질문을 확인하고 `architecture.svg` 또는 `architecture.png`를 엽니다.

요구사항을 입력하고 싶다면 [`.architecture/requirements.example.json`](.architecture/requirements.example.json)을 복사해 **`.architecture/requirements.json`**을 만들고, 수동 실행의 `requirements_file`에 해당 경로를 입력합니다. 실제 키·암호·개인정보를 요구사항 파일에 저장하지 마세요.

## 4. 요구사항 입력 예시

```json
{
  "workload": "auto",
  "deployment_preference": "auto",
  "environment": "dev",
  "data_classification": "internal",
  "region": "ap-northeast-2",
  "monthly_budget_usd": 200,
  "expected_monthly_requests": 100000,
  "availability_target_percent": 99.9,
  "rto_minutes": 240,
  "rpo_minutes": 60,
  "requires_authentication": true,
  "requires_relational_database": true
}
```

**이 값들은 사용 예시일 뿐**이며, 실제 프로젝트에 맞게 교체해야 합니다. 미입력 필드는 보고서의 질문으로 남습니다. 입력한 월 예산은 **AWS 예상 청구액이 아닙니다**. 사용자 입력과 코드 단서가 충돌하면 관련 경고를 출력합니다.

터미널에서 실행하려면 Python 3.10 이상과 Graphviz 바이너리를 설치하고 다음을 실행합니다.

```bash
python3 -m pip install -r requirements-diagrams.txt
python3 -m unittest discover -s tests -v
python3 scripts/recommend_architecture.py --repo . --output architecture-output --requirements .architecture/requirements.json
```

요구사항 파일을 만들지 않았다면 `--requirements` 옵션을 생략하세요. `--workload web`, `--budget 200`으로 수동 입력값을 덮어쓸 수 있습니다.

## 5. 외부 GitHub 저장소에서 사용

[`examples/aws-architecture.yml`](examples/aws-architecture.yml)을 대상 저장소의 `.github/workflows/aws-architecture.yml`로 복사합니다. 예시에는 흐름별 **한국어 주석**이 포함되어 있습니다. 요구사항 파일을 아직 추가하지 않았다면 해당 Action 입력을 생략하세요.

`uses: Leegiyeon/Generate-Architectures@main`은 최신 main 코드를 사용합니다. 운영 환경에서는 신뢰할 수 있는 **커밋 SHA 또는 버전 태그로 고정**하는 것을 권장합니다.

### GitHub App 배포 (별도 설치)

[`app/server.py`](app/server.py)는 서명 검증 웹훅으로 PR 이벤트를 수신해 **설치된 대상 저장소의 workflow_dispatch**를 호출하는 서버 코드입니다. GitHub App 등록, HTTPS 호스팅, 비밀 키 설정 및 저장소별 예시 워크플로 설치는 아직 자동화되지 않았습니다.

1. GitHub Developer Settings에서 App을 등록합니다. 저장소 권한은 **Actions: Read and write**, **Contents: Read-only**, **Pull requests: Read-only**로 최소 설정하고 PR 이벤트를 구독합니다.
2. Webhook URL을 `https://YOUR_HOST/webhook`으로 설정하고 별도의 Webhook secret을 생성합니다.
3. GitHub App ID, PEM private key, Webhook secret을 서버의 안전한 환경변수(`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`)로 제공합니다.
4. 저장소 루트에서 `docker build -f app/Dockerfile -t generate-architectures-app .`을 실행한 뒤 HTTPS 프록시 뒤에 배포합니다.
5. 앱을 대상 저장소에 설치하고 대상 저장소의 기본 브랜치에 `.github/workflows/aws-architecture.yml`을 배치합니다. 웹훅으로 실행할 때 `pull_request` 트리거를 유지하면 중복 실행될 수 있습니다.

## 6. 생성 결과물

| 파일 | 용도 |
| --- | --- |
| `recommendation.md` | 한글 설계 결정, 대안 비교, 확인 근거, 위험과 사용자 질문 |
| `repository-analysis.json` | 확인된 파일·기술·단서와 스캔 제한 |
| `requirements-used.json` | 실제 설계 판단에 사용한 사용자 입력 |
| `architecture.json` | 선택 패턴·대안·Well-Architected 검토 항목 |
| `architecture.png` | AWS 아이콘 다이어그램 이미지 |
| `architecture.svg` | AWS 서비스 아이콘이 내장된 독립 실행형 SVG |
| `architecture.dot` | Graphviz 원본 |

SVG는 디지털 문서용, PNG는 프레젠테이션용으로 사용할 수 있습니다. 다이어그램의 실선은 요청/데이터 흐름 **제안**, 점선은 보안 연계, 점선형 회색 선은 모니터링 연계를 나타냅니다. Diagrams의 AWS 아이콘은 최신 AWS 공식 아트워크와 다를 수 있습니다.

## 7. 보안과 한계

- 비밀키, `.env`, 전체 소스 전문을 OpenAI 등에 전송하지 않습니다. 기본 실행에는 외부 LLM API 키가 필요하지 않습니다. AI 보조 검토를 명시적으로 활성화한 경우에만 API 키가 필요합니다.
- 분석 파일 수는 최대 5,000개이며, 일부 알려진 설정 파일만 최대 64KB까지 읽어 기술 의존성을 확인합니다. 심볼릭 링크와 주요 빌드/의존성 폴더는 제외합니다.
- 현재 도구가 검증했다고 주장하는 것은 **입력 형식과 알려진 구조적 충돌**뿐입니다. AWS 계정, 서비스 가격, IAM, 취약점, 네트워크 실제 구성을 검사하지 않습니다.
- 연결된 패턴과 비용·보안·가용성의 판단 근거가 충분하지 않으면 반드시 전문가 검토가 필요합니다.
- 실제 코드와 다이어그램 사이의 완전한 일치, 내부망 배치, 다중 AZ 등은 가정으로 만들지 않습니다.

## 8. 개발 계획

- **완료(이번 단계):** 저장소 근거 기반 기술/데이터 단서 분석, 비기밀 요구사항 수집, 설계 대안 비교, 6원칙 검토 질문, 한국어 보고서, Actions 자동화.
- **다음 단계:** AST 분석 정확도 및 DB/외부연동 관계 추적, SSR 및 런타임 방식 추가 검증, 수집 근거에 대한 출처·신뢰도 표시.
- **후속 단계:** 리전·사용량 가정 기반 AWS Price List 비용 모델, 규칙 기반 IAM·네트워크/IaC 정책 검사, 부하·장애 복구 검증 지원.
- **장기 목표:** 인간 승인 필수인 IaC 제안 PR, GitHub App 운영 안정화, 멀티 클라우드 비교.

자세한 결정 기준은 [설계 문서](docs/ARCHITECTURE.md) 및 [로드맵](docs/ROADMAP.md)을 참고하세요. 과거 `generate_aws_architectures.py`는 레거시 실험용 스크립트이며 현재 Action 실행 경로에는 포함되지 않습니다.

## 9. P0 — 실제 소스코드 AST 기반 Application Graph (이번 개선)

이제 단순히 파일 이름만 탐지하는 데 그치지 않고, **Python AST + JavaScript/TypeScript Babel AST**로 함수·메서드·API Route·import·명시적 호출 관계를 분석합니다. 대상 저장소의 함수를 실행하지 않으며 원문·비밀키를 외부 AI API에 전달하지 않습니다.

산출물: `application-graph.json`(노드/간선·근거 파일 및 행·파싱 오류), `application-graph.svg`, `application-graph.png`, `application-graph.dot`. 기존 AWS 아이콘 기반 설계 제안도(`architecture.svg`)와 **구분**됩니다.

- **확인된 구조:** 정적 API 엔드포인트, 함수/메서드, 모듈 import, 확인된 직접 호출, Python SQLAlchemy/Django 계열 모델 후보, Prisma 모델 정의.
- **미확인 구조:** 동적 import, DI 주입 대상, 실제 네트워크·DB 호출, ORM 관계 전체, tsconfig alias, 런타임 리플렉션, Go/Java AST. 근거가 없으면 연결선을 그리지 않습니다.
- **보안/자원 상한:** 소스코드 실행 없음, 설치 스크립트 차단(`npm --ignore-scripts`), 최대 300개 소스 파일 및 파일당 64KB, 출력 노드/간선 수 제한. 다이어그램 표시량이 초과되면 JSON에 전체 추출 범위를 보존한 채 표시 제한 여부를 기록합니다.
- **실패 처리:** 일부 파일 구문 오류 또는 Node 파서 부재 시 `errors`에 명시하고, 가능한 다른 언어의 분석은 계속합니다. 파서 실패를 '연결 관계 없음'으로 해석하지 않습니다.

**직접 실행 준비:** Python, Node.js, Graphviz, `diagrams`를 설치한 뒤 `npm install --prefix scripts/js_analyzer --ignore-scripts --no-audit --no-fund --package-lock=false`를 먼저 실행합니다. GitHub Actions와 재사용 Action은 해당 설치를 자동 수행합니다. Node 또는 Babel을 설치할 수 없다면 Python AST만 분석하며 누락 사유를 결과 JSON에 기록합니다.

다이어그램은 구문 분석 결과를 이해하기 위한 참고 자료이며, AWS 설계 적합성이나 운영상의 호출/성능을 검증한 것으로 간주할 수 없습니다.

## 10. AI Solutions Architect Agent — 선택적 보조 검토

**기본은 비활성화이며, `workflow_dispatch` 수동 실행에서만 켤 수 있습니다.** 기존 `architecture.json`, AWS 아이콘 다이어그램, 규칙 기반 선정은 AI의 결과로 자동 변경되지 않습니다. 실제 AWS 인프라의 비용·보안·성능·적합성을 검증한 기능이 아닙니다.

### 동작 및 데이터 보호

1. 저장소 구조 분석, AST 그래프와 사용자가 명시한 요구사항을 **로컬에서 먼저** 처리합니다.
2. AI 전송 입력은 `true`인 기술 신호, 검증된 비기밀 요구사항, API/함수/모델 **개수**, 비교 가능한 배포 대안 및 E001 형태의 근거 ID로 **최소화**합니다. **원본 소스, 파일 경로/파일명, 함수명, 사용자 자유 입력, 저장소 이름, 토큰/키를 프롬프트에 넣지 않습니다.**
3. OpenAI Responses API의 Structured Outputs(JSON Schema, `store: false`)로 보조 의견, 다른 대안의 장단점, 미확인 위험, 사용자 확인 질문을 받습니다.
4. 모델이 선택한 대안의 적합 가능 여부와 근거 ID를 **애플리케이션에서 다시 검사**합니다. 모델이 허용되지 않은 대안을 선택하거나 알려지지 않은 근거를 참조하면 해당 결과를 폐기합니다. 근거 ID 일치가 내용의 사실성을 보증하지는 않습니다.
5. 호출 실패·키 없음·스키마 오류 시 원래 규칙 기반 추천을 변경하지 않고, AI 미실행/실패 사유만 파일에 남깁니다.

### 활성화

GitHub 저장소 **Settings → Secrets and variables → Actions**에서 `OPENAI_API_KEY`를 저장하고, Actions → AWS 아키텍처 검토 자동화 → Run workflow에서 `enable_ai=true`로 명시적으로 선택합니다. 기본 모델은 `gpt-6-luna`이며, 실제 모델 사용 권한·과금은 API 계정 정책에 따릅니다. **API 키가 아직 없다면 모델 호출은 수행되지 않습니다.**

외부 저장소에서 재사용하는 경우에도 `enable_ai: "true"`와 실행 단계에 `OPENAI_API_KEY` 환경변수를 **사용자가 직접** 전달해야 합니다. 자동 `push`/PR에서는 모델을 호출하지 않도록 메인 CI에서 강제 비활성화했습니다. AI 사용 시 전송 단서 자체가 외부 서비스로 전달된다는 점을 검토하세요.

### 결과물

- `ai-review.json`: `disabled` / `unavailable` / `error` / `reviewed_unverified` 상태, 검증된 구조화 의견과 E001 근거 ID
- `ai-review.md`: **한국어** AI 보조 검토, 대안, 위험, 미확인 질문, 근거 ID 카탈로그
- `recommendation.md`: AI 실행 여부를 한 줄로 표시하여 규칙 기반 설계와 구분

**현재 검증 범위:** 실제 API 비용을 발생시키는 E2E 호출을 수행하지 않으며, CI에서는 모의 응답(mock)과 오류/환각 방어 테스트를 실행합니다. 외부 모델의 실제 응답은 API 키와 허용 계정을 설정한 사용자가 수동으로 확인해야 합니다. AI는 AWS 자원을 생성하거나 배포하지 않습니다.
