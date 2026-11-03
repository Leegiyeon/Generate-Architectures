# 제품 로드맵: AI Solutions Architect Agent

> **2026-11-03 제품 방향 업데이트:** 기능 개수보다 사용성·정적 근거·안전한 마이그레이션 판단을 우선합니다. 최신 개발 우선순위는 **[간편한 AWS 설계·온프레미스 이전 MVP 로드맵](LEAN_MIGRATION_ROADMAP.md)**이 기준입니다. ① 간편 시작 [#33](https://github.com/Leegiyeon/Generate-Architectures/issues/33) → ② 온프레미스 Inventory/As-Is [#34](https://github.com/Leegiyeon/Generate-Architectures/issues/34) → ③ AWS Migration Assessment [#35](https://github.com/Leegiyeon/Generate-Architectures/issues/35) → ④ 사용자 보고서·시각 QA [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14). 기존 #15·#16은 검증/비용 고도화로 유지하고, 로컬 수집 [#36](https://github.com/Leegiyeon/Generate-Architectures/issues/36)과 AWS Inspector #17은 선택형 후속입니다. **신규 기능은 계획이며 아직 구현되지 않았습니다.**

> 아래는 구현 방향이며, **미완료 항목은 실제 제공 기능이 아닙니다.** SAA 자격 보유 전문가의 모든 판단을 자동 대체한다는 의미가 아닙니다.

## 현재 제품 방향 — Architecture Designer 우선 (Issue #9)

1. **핵심 Architecture Designer:** 사용자가 GitHub 저장소를 한 번 분석해 AWS 설계 초안, 선정 이유, 가정/위험, 다이어그램을 다운로드합니다. 재분석은 사용자가 선택합니다. push/PR은 자동 테스트만 수행합니다.
2. **상세 설계 고도화:** [#10](https://github.com/Leegiyeon/Generate-Architectures/issues/10) 근거 계약(기반 구현 완료) → [#11](https://github.com/Leegiyeon/Generate-Architectures/issues/11) 상세 AWS 토폴로지(논리 AWS 아이콘/네트워크 선택 규칙 기반 구현, 실환경 정책 검증 미완료) → [#12](https://github.com/Leegiyeon/Generate-Architectures/issues/12) 선정 근거(정적 매트릭스·DB 접근 전략·EC2 독립 To-Be·미승인 ADR 기반 구현) → [#13](https://github.com/Leegiyeon/Generate-Architectures/issues/13) 보안·트래픽·운영 전략(토폴로지 기반 청사진 구현, 실환경 검증 미완료) → [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14) 사용자 보고서 통합(오프라인 단일 HTML/4개 결과물·파일 무결성 기반, 시각 QA 추가 검토).
3. **비용·품질:** [#15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 후보별 비용/용량, [#16](https://github.com/Leegiyeon/Generate-Architectures/issues/16) 프로젝트 사례 E2E 검증.
4. **선택형 로컬 진단:** [#17](https://github.com/Leegiyeon/Generate-Architectures/issues/17) AWS CLI 읽기 전용 진단, [#18](https://github.com/Leegiyeon/Generate-Architectures/issues/18) Local UI. 사용자 계정 비밀키의 중앙 저장 없음.
5. **사용성:** [#19](https://github.com/Leegiyeon/Generate-Architectures/issues/19) GitHub App 설치/재분석 사용성. 상시 모니터링/배포 자동화는 현재 제품 범위에서 제외.

**아래 1~5차는 이전 기술 로드맵의 완료/미완료 상세 이력입니다.** 최신 우선순위는 위 Issues와 [제품 정의](PRODUCT.md)를 따르며, 예전 IaC 자동 생성 계획은 현 제품 범위에서 보류합니다.

## 1차 — 재현 가능한 근거 수집과 설계 초안 (이번 반영)

- [x] 설정 파일·API 디렉터리·DB/인증/작업 큐 단서 수집
- [x] 명시적 요구사항 JSON 검증 및 미확인 조건 질의
- [x] Static / Serverless / Container / Mobile 설계 대안과 선택 근거
- [x] 정적 Next.js 확정 오판 방지, 명시적 충돌 경고
- [x] Well-Architected 6개 영역의 검증 전 체크리스트
- [x] 한국어 보고서 및 아이콘 SVG/PNG
- [x] GitHub Actions 검증/Artifact 및 사용 예시
- [x] Python/JS/TS AST에서 직접 확인되는 API·함수 호출 관계 및 일부 모델 정의 그래프 생성 (기초 범위)
- [ ] DB 테이블 관계·외부 연동의 실제 실행 흐름 검증, Go/Java 정적 파서와 DI 추적

## 2차 — 코드 기반 아키텍처 그래프

1. [일부 완료] Python/JS/TS AST와 Prisma 모델 정의 탐지. [미완료] Go/Java 파서, OpenAPI·ORM 상세 관계 추출
2. [일부 완료] 확인 가능한 함수·API 호출의 경로/행 근거. [미완료] DI·외부 API·DB 실제 호출 연결 검증
3. SSR/SSG/ISR, 배치/큐, 비동기 처리 여부를 검증 가능한 규칙으로 탐지
4. [기반 구현 완료] evidence-contract.json으로 관찰/설정 단서/명시 입력/시스템 기본값/가정/미확인 및 파싱 오류·근거 시각을 분리
5. [일부 완료] AST 구조별 다이어그램 및 AWS VPC/상징 AZ 논리 토폴로지 별도 생성. [미완료] 근거와 서비스별 상세 네트워크 규칙·운영 검증 연결

**완료 기준:** 대표 프로젝트 10개에 대해 API·DB 연결 근거 누락/오탐을 수동 감사하고, 예외 사례를 테스트에 추가한다.

## 3차 — 아키텍처 의사결정 지원

- [x] 선택적 AI 보조 검토의 안전한 입출력 계약, 최소화된 비기밀 단서, 근거 ID 검증 및 결과 분리 (이번 구현)
- [ ] 실제 API 계정을 사용한 라이브 연결·비용 확인 (사용자 설정 필요)
- [x] 설계/요구사항 정합성 정적 검증 규칙, AI 결과 격리, ADR 초안 생성 (이번 단계)
- [ ] 실제 승인 워크플로, AWS 인프라/IaC 기반 보안·성능 검증

1. [JSON 입력 지원] RTO/RPO/SLO, 평균·피크 RPS, 피크 동시 연결, 지연 목표, 운영 우선순위·리전·데이터 분류. [미완료] 전용 입력 폼 UI
2. 서버리스 / Fargate / EC2 / 관리형 서비스 대안을 구체적 제약과 함께 비교
3. [기반 완료] EC2 포함 후보별 적합/차단/미확인, DB 접근 유형과 이전 제약, 별도 EC2 To-Be 논리도 및 출처 분리된 미승인 ADR. [미완료] 실배포/성능 데이터 기반 최적안 승인
4. [일부 완료] 명시적 요구와 참조 설계의 충돌은 차단. [미완료] 실제 IAM·네트워크 정책에서 위험 접근 확인

**완료 기준:** 시나리오별 금지 제약 검출과 대안 선택을 회귀 테스트로 검증.

## 4차 — 검증 엔진과 비용 산정

1. [기반 구현] 직접 입력한 공식 가격 출처·월간 사용량 및 명시적 AWS GetProducts 조회. [미완료] 실제 SKU 계층 요금·서비스 합계·사용량 범위 검증
2. [일부 완료] Terraform plan JSON의 명시적 공개 설정/과도한 IAM 권한 제한. [미완료] HCL/CDK/CloudFormation 전문 정책 검사 및 실환경 대조
3. [완료] 정적 검토, 입력 단가 및 AWS 계정 실측 미실시 상태 분리. 실제 계정 측 실측 증거 수집은 미완료
4. 6개 Well-Architected 원칙별 근거 포함 검토 현황
5. 예상치/측정치/검증 불가를 분리 표기

**완료 기준:** 다양한 리전·사용량의 공식 요금 사례와 교차검증하며, 거짓 적합 판정이 나오지 않도록 테스트.

## 5차 — 과거 계획 / 보류: IaC 생성과 GitHub App 자동화

1. [현재 범위 밖] Terraform/CDK 제안 PR 및 AWS 자동 배포 (사용자 필요시 별도 범위로 검토)
2. [선택형 로컬 진단으로 이전] AWS CLI Profile 기반 읽기 전용 진단 및 보안·감사 로깅 (#17~#18)
3. [후속] GitHub App 설치·권한·웹훅 멱등성·재시도·오류 복구 (#19)
4. [선택형] 최초 1회 분석 및 사용자 요청에 의한 재분석 이력 관리

**완료 기준:** 승인 전 자동 배포 없음, 최소 권한, 재시도해도 PR·댓글 중복 최소화, 테스트/감사 기록 제공.

## 우선순위

**코드 근거 정확성 > 설계 제약 충돌 방지 > 아키텍처 검토 가능성 > 비용 계산 > IaC 자동 생성.** 단순히 보기 좋은 다이어그램보다 잘못된 확신을 방지하는 설계가 더 중요합니다.

- [Issue #15](https://github.com/Leegiyeon/Generate-Architectures/issues/15): **비용 시나리오 v2 기반 구현** — 사용자가 최소/기준/피크의 월 사용량을 명시하면 동일한 검증 단가로 계산, AWS To-Be 서비스별 비용 분류 누락 및 리전 불일치 표시. **잔여:** 실제 SKU/계층 가격·처리량 기반 용량 및 서로 다른 서비스 대안 비용 신뢰도 검증.

- [Issue #16](https://github.com/Leegiyeon/Generate-Architectures/issues/16): **10종 가상 프로젝트 Golden CI 회귀 기반** 구축. 수동 브라우저 시각 QA·실제 오탐/미탐 분석/성능 실측은 남아 있음.

- [Issue #15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) **2차 진전**: Price List Query의 단일 SKU/단위에서 연속된 OnDemand 계층별 USD 가격·기준일 기록, 보수적 미지원 차원 차단 및 가상 공식 형식 회귀 추가. **미완료**: 공식 SKU별 라이브 검증/특별 계약·Free Tier·서비스 조합/대안 비교, 실제 워크로드 기반 용량.

- [Issue #15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 3차 진전: 사용자 제공 **동일 월 업무량의 ECS/EC2/Lambda 비용 항목 비교**, 서비스별 운영/보안/패치 책임, 요구사항·입력 금액·기본 비용 분류 충돌 차단 구현. **후속:** 동일 워크로드에서 실제 처리량/용량과 공식 리전별 SKU 가격 및 전체 청구 범위가 검증된 비교는 미완료.

- [Issue #15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 4차 진전: **사용자가 제출한 집계형 부하 테스트 데이터**로 대상 워크로드의 RPS/p95/오류율/시험 지속시간을 명시 목표와 비교, Lambda 이론 정상상태 동시성 및 옵트인한 ECS/EC2 선형 산술 계획 수량 참고. 요구 미달·후보 누락 시 비용 차액 표기 중단. **미완료:** 실제 AWS 부하/쿼터·운영 환경 성능 검증과 검증된 단가·정확한 필요 용량 및 서비스별 전체 비용 산정.
