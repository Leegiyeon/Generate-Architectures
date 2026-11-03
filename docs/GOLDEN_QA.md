# 대표 프로젝트 10종 골든 테스트·시각 QA (Issue #16 — 자동 검증 기반)

> 이 fixture들은 실제 고객 운영 저장소가 아니라 구조가 명확한 가상 예제입니다. 자동화가 검증하는 것은 **정적 코드 단서와 AWS 참조 설계 초안의 일관성**이며 실제 서비스의 보안/성능·비용/운영 적합성이 아닙니다.

## 골든 기준

| ID | 대표 구조 | 골든 선정 패턴 | 추가 확인 |
| --- | --- | --- | --- |
| 01 | Vite 정적 웹 | static | 정적 페이지 / VPC 미포함 |
| 02 | Next.js static export | static | export 설정만 정적 배포 |
| 03 | Next.js SSR | containers | 정적 단독 배포 미선정, 99.9% 목표 실측 아님 |
| 04 | FastAPI + Docker | containers | 정적 파서가 /health API 감지 |
| 05 | NestJS + Docker | containers | 실제 API/인가 정책은 미검증 |
| 06 | Prisma/PostgreSQL | containers | DB 단서 확인 / RDS는 제안만 |
| 07 | MongoDB(Mongoose) | containers | RDS 임의 변경 금지 / DB 자동 이전 없음 |
| 08 | Python Serverless | serverless | Lambda/API Gateway 후보만 |
| 09 | Expo mobile | mobile | 인증 불필요 명시 시 Cognito 제외 |
| 10 | 호스트 직접 제어·민감 데이터·고가용성 | containers (차단/검토) | Fargate 부적합 조건으로 승인 차단 |

## CI 자동 검증

tests/test_golden_workloads.py에서 10개 고정 fixture를 임시 저장소로 만들어 실제 **run() 전체 파이프라인**을 실행합니다.

- 선정 패턴 및 DB/서비스 노드·옵션 모순 여부
- 미확인 가격은 미산정, 보안/운영/ADR은 승인 전
- SVG XML/viewBox·내장 AWS 아이콘, PNG 서명/크기
- HTML 내부 링크, 실행 스크립트 미포함, Artifact 해시와 일치
- FastAPI AST API 경로 등 지원 가능한 근거 관측
- 지원 범위를 넘어 실제 운영 리소스/고객 데이터/클라우드 계정을 검사하지 않음

이것은 **10개 프로젝트 자동 회귀 테스트**이며, 인간이 시각적으로 직접 승인했다는 뜻이 아닙니다.

## 수동 화면 QA 실행 방법

### GitHub Actions (권장)

Actions → AWS 아키텍처 검토 자동화 → Run workflow → golden_qa=true를 지정합니다. 실행 완료 후 **aws-architecture-golden-fixtures** Artifact를 받아 golden-index.md의 10개 링크를 순차적으로 확인합니다. push/PR 자동 실행에서는 이 대량 보고서를 생성·업로드하지 않습니다.

### 로컬

`python3 tests/generate_golden_artifacts.py --output golden-output`

생성 결과에는 golden-index.md/json, 사례별 START-HERE.html, AWS 다이어그램 SVG/PNG, 선택·검증·보고서가 있습니다.

## 사람이 추가 확인해야 하는 항목

각 사례별로 ① 한글 문자·특수문자 깨짐 ② AWS 서비스 아이콘 선명도·누락 ③ 라벨/선 잘림·겹침 ④ 모바일 화면 폭·확대 ⑤ As-Is/To-Be 오인 가능성 ⑥ 미산정 가격/미검증 안내 ⑦ 브라우저별 링크/인쇄 보기를 확인합니다.

**수동 점검이 끝나기 전 golden-index.json의 manual_visual_review_completed는 false**로 유지됩니다. 이 상태에서 제품에 시각 QA 완료·프로덕션 사용 가능을 표시하지 않습니다. #14의 남은 시각 QA도 같은 검토 절차로 확인할 예정입니다.

## 후속 개선

- 실제 공개 저장소의 경로/함수 호출·기술 스택 오탐과 미탐 구분 및 커버리지 수치화
- 분석 성공률, AST 오류, 다이어그램 크기·서비스 교차 연결의 정상 범위 Golden Snapshot 관리
- 실제 브라우저 스크린샷에서 뷰포트 375/1440px 등 한글 클리핑/오버랩 확인
- #15 비용 SKU 기반 검증과 함께 실제 AWS 공식 계산 사례 비교

가상 fixture가 실서비스 적합성 90% 또는 정확도를 보장하는 것은 아닙니다.
