# 제품 로드맵: AI Solutions Architect Agent

> 아래는 구현 방향이며, **미완료 항목은 실제 제공 기능이 아닙니다.** SAA 자격 보유 전문가의 모든 판단을 자동 대체한다는 의미가 아닙니다.

## 현재 제품 방향 — Architecture Designer 우선 (Issue #9)

1. **핵심 Architecture Designer:** 사용자가 GitHub 저장소를 한 번 분석해 AWS 설계 초안, 선정 이유, 가정/위험, 다이어그램을 다운로드합니다. 재분석은 사용자가 선택합니다. push/PR은 자동 테스트만 수행합니다.
2. **상세 설계 고도화:** [#10](https://github.com/Leegiyeon/Generate-Architectures/issues/10) 근거 계약 → [#11](https://github.com/Leegiyeon/Generate-Architectures/issues/11) 상세 AWS 토폴로지 → [#12](https://github.com/Leegiyeon/Generate-Architectures/issues/12) 선정 근거 → [#13](https://github.com/Leegiyeon/Generate-Architectures/issues/13) 보안·트래픽·운영 전략 → [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14) 사용자 보고서 통합.
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
4. 수동 확인 항목과 도구가 관찰한 사실을 구분해 신뢰 수준 표시
5. [일부 완료] AST 구조 별도 다이어그램 생성. [미완료] 모듈별 상세도·AWS 후보 서비스와의 검증된 연결

**완료 기준:** 대표 프로젝트 10개에 대해 API·DB 연결 근거 누락/오탐을 수동 감사하고, 예외 사례를 테스트에 추가한다.

## 3차 — 아키텍처 의사결정 지원

- [x] 선택적 AI 보조 검토의 안전한 입출력 계약, 최소화된 비기밀 단서, 근거 ID 검증 및 결과 분리 (이번 구현)
- [ ] 실제 API 계정을 사용한 라이브 연결·비용 확인 (사용자 설정 필요)
- [x] 설계/요구사항 정합성 정적 검증 규칙, AI 결과 격리, ADR 초안 생성 (이번 단계)
- [ ] 실제 승인 워크플로, AWS 인프라/IaC 기반 보안·성능 검증

1. RTO/RPO/SLO, 트래픽·피크, 민감 데이터, 리전 제약 및 운영역량을 폼으로 수집
2. 서버리스 / Fargate / EC2 / 관리형 서비스 대안을 구체적 제약과 함께 비교
3. [초안 완료] 설계 결정 기록(ADR): 선택 사유, 제외 사유, 가정과 미검증 조건 분리
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
