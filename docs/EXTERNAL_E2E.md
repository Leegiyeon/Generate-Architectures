# 별도 사용자 저장소 Actions E2E

확인일: 2026-11-03. [결틈의 실제 수동 실행](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177)이 성공했다. 신규 AWS, Inventory 없는 이전, 선언형 Inventory가 있는 이전의 세 보고서를 생성하고, 다운로드한 Artifact의 HTML을 CI Chromium에서 18개 화면 상태로 검사했다.

## 실행 범위와 재현 근거

- 대상 소스: [oneul-ui-gyeol `4f25d290`](https://github.com/Leegiyeon/oneul-ui-gyeol/tree/4f25d2906639e42faa7712dc5542001a92e4100f).
- 임시 QA 브랜치의 [워크플로 `b5a07315`](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/b5a07315b871a58946ff98a863ab5179080b1474/.github/workflows/ci.yml)를 GitHub Actions의 Run workflow 버튼으로 실행했다. 기본 브랜치와 운영 배포 Workflow는 변경하지 않았다.
- 분석 Action 및 브라우저 검사 도구는 Generate-Architectures의 [`500341b2`](https://github.com/Leegiyeon/Generate-Architectures/commit/500341b2f431b9012002d4746b5f6f9b5727e5d6)에 고정했다. 이 실행은 이후 분석기·연결표·시각 수정의 검증을 대신하지 않는다.
- 실제 앱 설치·실행, DB 접속, 배포, AWS 계정 조회 및 OpenAI 호출은 수행하지 않았다. 앱용 시크릿도 전달하지 않았다.
- Inventory는 실제 서버 조사 결과가 아닌 **합성 선언 입력**이다. Linux 앱 별칭 하나와 PostgreSQL DB 별칭 하나, 선언된 database 연결 한 개를 사용했다.

## 결과

| 모드 | 결과와 경계 | Artifact |
| --- | --- | --- |
| `new_aws` | 신규 구축 보고서, 자동 배포/승인 없음 | [new-aws](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177/artifacts/13227836749) |
| `migrate_onprem`, Inventory 없음 | `needs_inventory`, 기존 인프라를 생성하지 않음 | [migration-unknown](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177/artifacts/13228535232) |
| `migrate_onprem`, 합성 선언 입력 | 정적 검토 초안, 실제 이전 검증 아님 | [migration-declared](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177/artifacts/13227342851) |

각 실행은 목적·미승인/미배포/미검증 상태, AI 비활성화 및 구조 QA 성공을 확인했다. 후속 CI job은 세 Artifact를 다운로드하여 1440/390/320px × 상세 닫힘/펼침을 검사했다. **3 reports, 18 rendered states passed** 로그와 [화면 Artifact](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177/artifacts/13228660088)를 보관했다. Artifact 보존 기간은 7일이며, 실행·고정 소스 링크는 별도 근거다.

`migration-declared` ZIP을 로컬 임시 폴더에도 내려받아 Chrome으로 6개 화면 상태를 검사했고 모두 통과했다. 실제 사용자 저장소에서 실행→Artifact 다운로드→오프라인 HTML 브라우저 검사의 제한된 E2E다. 비공개 저장소 권한, 모든 프레임워크 정확도, 사람이 수행한 시각 승인 및 AWS 구축 적합성까지 증명하지 않는다.

## 네트워크와 CI 정책

기본 분석은 외부 AI·AWS 계정·실시간 가격 API를 호출하지 않지만, Actions 실행 준비에는 GitHub checkout/Action 다운로드와 패키지·폰트·Graphviz·Playwright 설치 네트워크가 필요하다. 따라서 전체 Workflow가 네트워크를 전혀 사용하지 않는다고 설명하면 안 된다. 생성된 HTML의 브라우저 검사에서는 외부 HTTP(S) 요청을 차단하고 요청이 없음을 검사한다.

Generate-Architectures `main` 조회 결과 `protected=false`, repository rulesets는 빈 배열이었다. 관리 권한이 필요한 branch protection 상세 조회는 GitHub App 권한 제한으로 403이었다. **필수 CI 상태를 통한 병합 차단은 현재 강제되지 않는다.** CI 성공을 확인한 후 병합하는 운영 절차와 강제 정책은 구분한다. 저장소 설정을 이번 검사에서 변경하지 않았다.
