# 사용자용 AWS 아키텍처 설계 보고서 — Issue #14

> Generate-Architectures의 목적은 개발자의 중간 JSON·DOT를 직접 비교하는 것이 아니라, GitHub 저장소 분석 후 **AWS 설계도·선정 이유·보안/운영 방안·비용/용량의 불확실성**을 한 곳에서 검토하도록 하는 것입니다.

## 어떻게 실행하나요?

GitHub → Actions → **AWS 아키텍처 검토 자동화** → **Run workflow** → 결과 **Artifacts: aws-architecture-recommendation** ZIP 다운로드.

압축을 풀고 **START-HERE.html**을 브라우저에서 먼저 엽니다. 별도 서버, 로그인, AWS 자격증명 또는 외부 CDN이 필요하지 않습니다. HTML은 외부 자원 요청과 실행 스크립트를 포함하지 않는 오프라인 파일입니다. 동일 내용을 GitHub/텍스트 미리보기로 확인하려면 **START-HERE.md**를 엽니다.

### 처음 열면 보이는 순서

1. **요약**: 선정한 참조 패턴, 차단 항목 수, 미확인 질문, 실제 비용 산정 여부.
2. **AWS To-Be 설계도**: VPC/상징 AZ/서비스를 설명하는 통합 논리 다이어그램. 사용자가 SVG 확대 또는 PNG 출력 가능.
3. **서비스 선정 근거**: 현재 검토 패턴의 이유와 EC2/Lambda/Fargate/정적 후보 등 적용/제외 조건, DB 접근 패턴/ADR.
4. **Security & Operations**: AWS 노드에 연결한 IAM/SG/Secrets/Auto Scaling/CloudWatch/백업/롤백 제안. 실제 부하 측정값·서비스 쿼터·보안 검증 결과는 미포함.
5. **Cost & Capacity**: 사용자 제공 SKU/단가·요금 기준일과 사용량만 비교, 미산정 항목·지연/RPS/쿼터 미확인을 명시.
6. **As-Is vs To-Be**: 실제 소스에서 정적으로 관찰한 근거, 추정 단서, 사용자가 직접 입력한 값, 설계 제안, 실행하지 않은 검증을 별개로 표시.
7. **재분석**: 부족한 정보 목록과 요구사항 수정 → Actions 수동 재실행 경로 안내.

## 4개 주요 산출물

| 위치 | 내용 |
| --- | --- |
| deliverables/01-aws-to-be.svg / .png | 상세 AWS 네트워크·서비스 논리 설계도 |
| deliverables/02-architecture-decisions.md | 선정·제외/DB 대안·ADR 통합 기록 |
| deliverables/03-security-operations.md | 네트워크/IAM·모니터링·확장/복구 확인 항목 |
| deliverables/04-cost-capacity.md | AWS 요금/사용량의 입력 범위와 미산정 항목, 용량 근거 |

**artifact-index.json**은 각 주 결과물의 상대경로, 파일 해시(SHA-256), 참조 설계의 패턴·상태, 관찰 근거 수와 비용 계산 상태를 기록합니다. 생성된 SVG/PNG와 보고서가 **동일한 AWS 토폴로지 결과**를 가리키는지 파이프라인에서 검증합니다.

세부 JSON, DOT, 코드 AST, Terraform 정적 점검/AI(옵션) 결과 등의 기존 개발자용 파일들은 하위 호환성을 위해 **출력 루트에서 그대로 유지**합니다. EC2 대안은 기존처럼 ec2-alternative/에 별도 생성되며 현재 추천 AWS 구성을 자동 변경하지 않습니다.

## 보안/정확성 경계

- 저장소의 데이터나 민감 코드를 원격 보고용 서비스로 업로드하지 않습니다. HTML에 원격 JavaScript·CSS·이미지 의존성을 넣지 않고 SVG를 data URI로 내장합니다.
- 사용자/저장소 유래 텍스트는 HTML 이스케이프하여 스크립트로 실행되지 않도록 처리합니다. 다만 GitHub Actions Artifact는 권한 있는 저장소 사용자에게 노출될 수 있으므로, 보고서에 포함된 기술 구성/코드 경로 자체의 기밀 수준은 검토해야 합니다.
- AWS 계정 조회, AWS 배포/자원 변경, 부하 테스트, 보안 인증, 복원 테스트, SLA·SLO 보증은 수행하지 않습니다.
- 비용 입력이 일부만 산정되면 **부분합만** 표시하고 누락된 항목을 0원으로 간주하지 않습니다. 입력 항목이 모두 계산되더라도 **AWS 인프라 전체 총액이라고 표시하지 않습니다**.
- 사용자가 입력하지 않은 환경(dev 등)의 기본값은 **시스템 기본값**이지 명시적 승인 사항이 아닙니다.
- 최종 ADR은 항상 **proposed_pending_human_approval**이며 승인자/승인일은 비워 둡니다.
- 선택한 후보, 토폴로지 상태, ADR/정적 검토 게이트, 서비스별 경보 대상과 실제 To-Be 노드가 충돌하면 사용자용 보고서 생성을 거부합니다.

## 품질 확인

자동 테스트에서는 모든 참조 패턴(Static/Serverless/Mobile/Container)의 주요 파일 생성, 이미지/해시 일치, HTML 내부 링크, 외부 리소스/스크립트 차단, 입력 없는 비용의 미산정 표시, 일부 단가의 부분합, 악성 HTML 문자열의 이스케이프, 선택 게이트/토폴로지 불일치를 점검합니다.

**추가 수동 QA:** 실제 서비스 사용자 화면에서 SVG 복잡도/가독성, 한글 줄바꿈, 모바일 확대, 각 브라우저 파일 보안 제한 등을 확인해야 합니다. CI 자동 테스트만으로 이미지의 모든 시각적 품질이나 실제 AWS 구축 적합성을 보증하지 않습니다.

## 후속 개발

- **#15** AWS 서비스/SKU·시나리오(최소/기준/피크)의 실제 비용/용량 비교는 별도 과제입니다. 이 보고서는 현재 지원하는 비용 입력 범위를 충실하게 표시합니다.
- **#16** 대표 저장소 10종의 구조/그래프/보고서 시각 감사와 Golden E2E 테스트가 필요합니다.
- **#17~#18** 선택형 로컬 읽기 전용 AWS Account Inspector(미구현)는 이 보고서의 AWS 설계 제안과 실제 계정을 향후 비교하기 위한 별도 기능입니다.

## 3단계 비용 시나리오 연계 (#15 기반)

사용자가 선택한 v2 비용 파일은 **minimum / baseline / peak** 월 사용량을 분리합니다. START-HERE.html의 비용 섹션과 deliverables/04-cost-capacity.md에 시나리오별 입력 항목 부분합·완결 항목 합계·미산정 단가·To-Be 비용 분류 누락을 표시합니다. 사용자가 입력하지 않은 단가/사용량을 임의 채우거나 실제 AWS 비용으로 표시하지 않습니다. 자세한 검증 범위는 [COST_SCENARIOS.md](COST_SCENARIOS.md).

## 대표 10종 오프라인 시각 QA 옵션

workflow_dispatch의 `golden_qa=true`는 실제 운영 저장소가 아닌 고정 가상 fixture 10종에 대한 START-HERE.html/SVG/PNG 결과를 별도 Artifact로 만듭니다. 코드를 자동 배포하지 않으며 GitHub Actions 기본 수동 설계 실행에 영향을 주지 않습니다. 확인 절차는 [GOLDEN_QA.md](GOLDEN_QA.md) 참고. **인간의 시각 검수 완료 전에는 QA 완료로 표시하지 않습니다.**

## 동일 워크로드 대안 비교 (#15)

선택적 비교 입력 `alternative_cost_input`이 지정되면 사용자 HTML/Markdown의 비용 영역에 ECS Fargate/EC2/Lambda 대안의 입력된 월 비용·미확정 요금/서비스 분류·유지보수 책임을 표시합니다. 모든 단가·요구사항·비용 분류가 확인됐을 때에만 **입력 항목 한정 차액**을 표시하고, 실제 AWS 비용 우열·서비스 변경/자동 승인은 수행하지 않습니다. [이용 방법](ALTERNATIVE_COST_COMPARISON.md).

## 사용자 부하 시험 집계 기반 용량 근거 (Issue #15)

수동 Action 입력 capacity_evidence가 있는 경우 START-HERE.html에 AWS 후보별 RPS, p95(ms), 오류율, 제한된 시험 기준 충족 상태를 표로 표시하고, 추가 보고서 capacity-evidence.md를 제공합니다. 기존 비용 상세 deliverables/04-cost-capacity.md에도 집계된 확인 사항을 합칩니다. 이 자료가 제출된 테스트의 진위/동등성·실서비스 부하/오토스케일/Service Quotas 또는 AWS 자원 배포를 보증하지는 않습니다. [가이드](CAPACITY_EVIDENCE.md).

## 첫 화면 간소화와 자동 구조 품질 검사 (2026-11-03)

`START-HERE.html`은 첫 화면에 선택한 목적·권장 참조 패턴·차단 상태·비용 미산정 여부를 먼저 보여줍니다. 이어 기존 구성(온프레미스인 경우), AWS To-Be, 주요 선정/제외 이유, 보안·운영, 비용·다음 행동 순서로 검토합니다. 추가적인 비용 항목, 보안 통제 리스트, Rehost/Replatform 서버별 상세 변경표는 **외부 JS가 필요 없는 펼침 영역(details)**으로 제공합니다. 사용자가 입력하지 않은 비용/부하 데이터는 확대 테이블을 만들지 않습니다.

매 분석 실행 시 `report-qa.json` 생성 전 검증이 실패하면 결과 생성 자체를 오류로 처리합니다. 확인하는 항목은 오프라인 HTML 내부 앵커·파일 링크, 이미지 ALT/CSP/외부 스크립트 금지, AWS/As-Is SVG XML+viewBox, PNG 헤더·해상도, 토폴로지 노드/엣지 참조 일치, Artifact 해시, 신규/이전 모드별 미검증 메시지입니다.

**중요:** `status=automated_structural_checks_passed`는 파일 구조 QA만 성공했다는 뜻이며 `browser_rendered=false`, `manual_visual_review_completed=false`, `real_repository_accuracy_audited=false`, `aws_account_checked=false`를 유지합니다. 실제 데스크톱/모바일 화면의 한글·폰트·아이콘·클리핑 수동 감사와 외부 실제 저장소 분석 정확도 검증은 #14/#16의 후속 작업입니다.

## 실제 브라우저 회귀 검사

CI는 고정 Playwright 버전과 Chromium으로 합성 보고서 13종을 렌더링합니다. 기존 골든 10종에 Inventory 없음, 8개 서버의 선언형 As-Is, 비용 입력 상세가 있는 이전 모드를 추가했습니다. 각 보고서를 1440px·390px·320px에서 상세 닫힘/펼침 두 상태로 검사합니다.

- 실제 이미지 디코딩 및 표시 크기, 페이지 가로 넘침, 작은 안내 글자 대비 4.5:1 이상.
- 키보드 Enter로 모든 summary 열기/닫기, Unicode 대체문자 및 브라우저 실행 오류.
- 외부 HTTP(S) 요청 차단 및 요청 발생 시 실패. 분석 대상 프로젝트 자체는 실행하지 않습니다.
- `report-browser-qa` CI Artifact에 전체 화면 PNG와 `browser-qa.json` 보관(7일). 실패한 재실행은 이전 성공 상태를 유지하지 않습니다.

로컬 실행에는 기존 Python/Graphviz/Babel 분석 의존성과 아래의 선택적 브라우저 검증 도구가 필요합니다.

```bash
npm ci --prefix scripts/browser_qa --ignore-scripts --no-audit --no-fund
scripts/browser_qa/node_modules/.bin/playwright install chromium
python3 tests/generate_golden_artifacts.py --output browser-fixtures
python3 tests/generate_browser_fixtures.py --output browser-fixtures
node scripts/browser_qa/audit.cjs browser-fixtures browser-qa-output
# 설치된 Chrome을 사용하려면 앞에 BROWSER_QA_CHANNEL=chrome 지정
```

추가 브라우저 검사의 `browser-qa.json`만 `browser_rendered=true`를 기록합니다. 개별 분석의 기존 `report-qa.json`은 **브라우저를 실행하지 않았으므로 변경하지 않습니다**. 자동 화면 검사는 한글 글꼴의 모든 글리프·도면 내부의 선/라벨 겹침·AWS 설계의 적합성을 판정하지 않습니다. `manual_visual_review_completed=false`와 `aws_account_checked=false`를 유지합니다. 복잡한 모바일 도면은 `SVG 확대`로 열어 확대해서 확인하세요.

실제 공개 코드 샘플 1건의 수동 근거 대조 결과는 [REPORT_QA_AUDIT.md](REPORT_QA_AUDIT.md)를 참고하세요. 13개 합성 fixture의 통과율을 실제 저장소 검출 정확도로 해석하면 안 됩니다.
