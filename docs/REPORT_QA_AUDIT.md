# 보고서 브라우저 검증 및 공개 코드 감사

기준일: 2026-11-03 (Asia/Seoul). Issue #14, #16의 제한된 후속 검증입니다.

## 재현 범위

- 분석기 기준: `531ae209b01816d8b4bf3e0192241835fce560a0` 이후 보고서 안내 글자 대비 수정 및 브라우저 회귀 검사 추가.
- 로컬 환경: macOS ARM64, Python 3.12, Graphviz 14.1.2, Playwright 1.62.1, Chrome 156.0.8078.80.
- 합성 보고서 13종 × 너비 1440/390/320px × 상세 닫힘/펼침 = **78개 화면 상태** 자동 검사 통과.
- 작은 안내 글자의 대비 부족을 확인하여 흰 패널의 보조 글자를 어둡게, 어두운 헤더의 보조 글자를 밝게 변경했습니다. 도면 자체는 별도 SVG 확대 링크로 읽습니다.
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

## 남은 검증

- 이 감사는 실제 저장소 1건이며 열 가지 제품 유형의 정확도나 오탐/미탐률을 대표하지 않습니다.
- 브라우저 자동 검사와 일부 화면의 시각 관찰은 모든 도면의 한글 글리프·아이콘·선/라벨 겹침 수동 승인과 다릅니다. 사람의 전체 시각 검수 완료 상태는 계속 false입니다.
- 별도의 사용자 저장소에서 Actions 버튼 실행 → Artifact 다운로드 → 브라우저 열기의 전체 E2E는 미수행입니다(#33/#34).
- 실제 AWS 계정·DB 연결·성능·보안·비용·이전 다운타임·배포는 검증하거나 변경하지 않았습니다.
