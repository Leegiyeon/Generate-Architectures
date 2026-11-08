# 보고서 브라우저 검증 및 공개 코드 감사

기준일: 2026-11-03 (Asia/Seoul). Issue #14, #16의 제한된 후속 검증입니다.

## 2026-11-08 도면 라벨 보완

`5345244c` 이후 상세 AWS 도면에서 서비스 이름이 아이콘 하단에 겹치는 문제를 재현했습니다. 기존 FastAPI 샘플의 Chrome SVG 글자 경계는 아이콘 아래쪽과 약 14.1px 겹쳤습니다. 모든 서비스에 고정 아이콘 행과 별도 이름 행을 적용해 크기와 라벨 공간을 분리했습니다. 애플리케이션 도면에 문자 그대로 보이던 `\n`도 이름/소스 위치 두 줄로 수정했습니다.

최대 길이 24자 온프레미스 별칭과 역할을 같은 행에 놓으면 카드 밖으로 나가는 문제도 확인했습니다. 별칭·역할·CPU·RAM·스토리지·DB·접근에 공간을 나눠 원문 값을 생략하지 않습니다. 최대 8서버/16연결과 정밀 소수 입력의 실제 Chrome 텍스트 경계 73개가 카드/연결 영역 안에 들어왔습니다.

- Python 회귀 테스트 224개 통과. 지원 아이콘 전체의 실제 SVG 좌표, XML 특수문자 보존, 애플리케이션 두 줄 출력, 최대 Inventory 입력을 검사합니다.
- 합성 보고서 13종·78화면 통과. 브라우저에서 내장 SVG를 측정해 아이콘/이름 간격 최소 2 SVG 좌표 단위와 카드 경계를 검사합니다. 이 실행에서 최소 간격은 약 8.89 SVG 좌표 단위였습니다. 실제 출력 위치/글꼴 경계로 검사하며 전체 도면 배치의 점수는 아닙니다.
- 같은 고정 NestJS/FastAPI 소스로 다시 생성한 보고서 2종·12화면 통과. 소스 커밋은 [실제 저장소 감사](REAL_REPOSITORY_AUDIT.md)와 같습니다. 이전 분석의 부분 파싱·미지원 범위도 유지됩니다.
- 로컬 재현 산출물: `browser-fixtures/diagram-layout`, `browser-qa-output/diagram-layout`, `browser-fixtures/diagram-real`, `browser-qa-output/diagram-real` (Git 제외).

PNG·SVG 및 화면을 에이전트가 확인했지만 사람의 전체 시각 승인이 아닙니다. 간선과 라벨 교차, 모든 한글 글리프, AWS 적합성은 자동 판정하지 않으며 `manual_visual_review_completed=false`를 유지합니다.

## 재현 범위

- 분석기 기준: `531ae209b01816d8b4bf3e0192241835fce560a0` 이후 보고서 안내 글자 대비 수정 및 브라우저 회귀 검사 추가.
- 로컬 환경: macOS ARM64, Python 3.12, Graphviz 14.1.2, Playwright 1.62.1, Chrome 156.0.8078.80.
- 합성 보고서 13종 × 너비 1440/390/320px × 상세 닫힘/펼침 = **78개 화면 상태** 자동 검사 통과.
- 작은 안내 글자의 대비 부족을 확인하여 흰 패널의 보조 글자를 어둡게, 어두운 헤더의 보조 글자를 밝게 변경했습니다. 도면 자체는 별도 SVG 확대 링크로 읽습니다.
- 첫 Linux Chromium CI에서 320px 화면의 가로 넘침을 발견하여 긴 문자열도 줄바꿈하는 공통 규칙을 추가했습니다. 검사 실패 화면과 넘친 요소 정보도 보관합니다.
- 결과와 스크린샷은 로컬 `browser-qa-output/`, CI에서는 `report-browser-qa` Artifact로 확인합니다. 실행하지 않은 CI 성공을 이 기록으로 대신하지 않습니다.

## 실제 공개 저장소 1건 — 결틈

샘플: [Leegiyeon/oneul-ui-gyeol, 4f25d29](https://github.com/Leegiyeon/oneul-ui-gyeol/tree/4f25d2906639e42faa7712dc5542001a92e4100f).

앱과 의존성 설치 스크립트를 실행하지 않고 정적 분석만 수행했습니다. 검사 파일 124개, 스캔 잘림 없음. 에이전트가 소스 근거를 읽고 결과와 대조한 제한된 감사이며 전체 파일의 정답 집합이나 검출 성공률을 산출하지 않았습니다.

| 항목 | 소스 근거 | 분석 결과와 한계 |
| --- | --- | --- |
| Next.js 서버 구성 | [package.json](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/package.json#L22)의 Next.js, [next.config.ts](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/next.config.ts#L4)의 standalone | `nextjs=true`, `next_static_export=false`, `static_candidate=false`. 컨테이너 참조 패턴 제안. 실제 AWS 적합성은 미검증. |
| API 경로 | [game/route.ts](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/src/app/api/game/route.ts#L9)의 GET 등 | AST 경로 11개 관찰. 경로 기반 단서는 12개이며 `route.test.ts`도 포함하므로 **실제 API 수와 동일하지 않음**. 이 경로 기반 오탐은 후속 수정 대상. |
| 관계형 DB | [schema.prisma](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/prisma/schema.prisma#L5)의 PostgreSQL, [db.ts](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/src/lib/db.ts#L5)의 PrismaClient | `relational_database=true`, Prisma 엔진 근거 연결. 실제 DB 연결·서버 위치·데이터 크기는 확인하지 않음. |
| 자체 관리자 인증 | [admin-auth.ts](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/src/lib/admin-auth.ts#L28)의 비밀번호 비교·서명 쿠키, [로그인 API](https://github.com/Leegiyeon/oneul-ui-gyeol/blob/4f25d2906639e42faa7712dc5542001a92e4100f/src/app/api/admin/login/route.ts#L15) | `authentication_library=false`: 알려진 인증 라이브러리 미탐지. 자체 인증의 존재를 자동 검출하지 못함. 인증 필요 여부 질문과 `authentication_not_confirmed`를 유지하며 **인증 없음/보안 통과를 뜻하지 않음**. |

## 후속 수정·감사 (2026-11-03)

위 표는 PR #44 시점의 감사다. 이후 경로 분석과 AST 분석이 공통 테스트 파일 제외 규칙을 사용하도록 수정했다. 결틈의 `route.test.ts`가 API 경로 근거에서 제외되어 12개에서 11개로 줄었고, 실제 핸들러 경로는 보존했다. 자체 인증은 여전히 자동 검출하지 못하므로 인증 라이브러리 미탐지가 인증 부재를 뜻하지 않는다는 안내와 확인 질문을 강화했다.

공식 NestJS·FastAPI 저장소 두 개의 고정 소스 감사는 [REAL_REPOSITORY_AUDIT.md](REAL_REPOSITORY_AUDIT.md), 별도 사용자 저장소의 실제 Actions 실행·Artifact 다운로드 및 브라우저 검사는 [EXTERNAL_E2E.md](EXTERNAL_E2E.md)에 기록했다. 세 사례로 전체 검출 정확도나 재현율을 산출하지 않는다.

에이전트가 기존 13종 데스크톱 화면 및 일부 모바일·원본 도면을 직접 열어 관찰한 결과, 모바일 이전 표의 과도한 줄바꿈과 사용자 아이콘/라벨 겹침을 발견했다. 이 관찰은 자동 overflow 검사나 사람의 승인과 구분한다.

후속 수정으로 모든 HTML 표에 내부 스크롤과 최소 너비 640px을 적용하고, 사용자 아이콘과 라벨을 별도 행으로 분리했다. 도면 글자 크기도 소폭 키웠다. 새로 생성한 합성 13종의 78개 Chrome 화면 상태가 통과했고, 표의 최소 너비·스크롤 실제 동작·스크롤 영역의 viewport 경계도 검사했다. 사용자 라벨이 아이콘 아래로 떨어져 있는지는 실제 SVG 좌표 회귀로 확인한다. 최종 Python 테스트 200개도 통과했다. 사람의 시각 승인과 AWS 검증 상태는 변경하지 않는다.

## 남은 검증

- 이 문서의 최초 감사는 실제 저장소 1건이며, 후속 2건까지 포함해도 열 가지 제품 유형의 정확도나 오탐/미탐률을 대표하지 않습니다.
- 브라우저 자동 검사와 일부 화면의 시각 관찰은 모든 도면의 한글 글리프·아이콘·선/라벨 겹침 수동 승인과 다릅니다. 사람의 전체 시각 검수 완료 상태는 계속 false입니다.
- 별도 공개 사용자 저장소의 제한된 Actions E2E는 후속 실행으로 확인했습니다. 비공개 저장소 권한과 실제 온프레미스 서버 입력의 진위는 미검증입니다(#33/#34).
- 실제 AWS 계정·DB 연결·성능·보안·비용·이전 다운타임·배포는 검증하거나 변경하지 않았습니다.
