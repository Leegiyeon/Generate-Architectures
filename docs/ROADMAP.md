# Generate-Architectures — 개발 우선순위

> 기준: **사용자 시작의 단순성 → 관찰 가능한 근거 → AWS 설계/이전의 판단 가치 → 검증 가능성**.
> 과거 장문의 작업 이력은 GitHub Issue와 PR에 남아 있습니다. 이 문서는 **현재 개발 순서만** 관리합니다.

| 순서 | 우선순위 | 업무 | 상태 |
| --- | --- | --- | --- |
| 1 | P0 | [#33](https://github.com/Leegiyeon/Generate-Architectures/issues/33) 신규 AWS/온프레미스 이전 2모드 + 최초 실행 UX | 외부 저장소에서 신규·이전 입력 없음·이전 Inventory 입력 3경로의 Actions/Artifact/브라우저 검사 통과; 이용 환경 확대 검증 필요 |
| 2 | P0 | [#34](https://github.com/Leegiyeon/Generate-Architectures/issues/34) 최소 On-Prem Inventory + As-Is | 선언형 As-Is와 실제 브라우저 회귀 구현; 도면 전체 수동 승인·실제 서버 진단 미완료 |
| 3 | P0 | [#35](https://github.com/Leegiyeon/Generate-Architectures/issues/35) Migration Assessment·변경사항/위험 | Rehost·Replatform 서버·선언 연결별 변경표 구현; 실제 연결/이전 적합성 미검증 |
| 4 | P0 | [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14) 단일 사용자 보고서·시각적 QA | 합성 보고서 13개·78화면 자동 검사와 외부 보고서 3개·18화면 통과; 모바일 표·도면 라벨 수정·자동 회귀 통과, 수동 시각 승인 필요 |
| 5 | P1 | [#16](https://github.com/Leegiyeon/Generate-Architectures/issues/16) 실제 사례 오탐·미탐/시각 QA | 테스트 API 오탐 수정, 실제 공개 저장소 3개 감사; Python DB·NestJS API 등 미탐과 필수 CI 강제 정책 미해결 |
| 6 | P1 | [#15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 비용·용량·공식 SKU 검증 | 공식 예시 3건 산술 회귀 추가; 실제 SKU·전체 비용·부하/용량 실측 검증 미완료 |
| 7 | 선택 | [#36](https://github.com/Leegiyeon/Generate-Architectures/issues/36) 로컬 온프레미스 최소 진단 | 미구현 |
| 8 | 후속 | [#17](https://github.com/Leegiyeon/Generate-Architectures/issues/17) 로컬 AWS 읽기 전용 진단 | 미구현 |

별도 로컬 웹 UI([#18](https://github.com/Leegiyeon/Generate-Architectures/issues/18))와 GitHub App([#19](https://github.com/Leegiyeon/Generate-Architectures/issues/19))은 MVP에서 **보류**합니다.

## 2026-11-03 검증 진전과 다음 작업

외부 결틈 저장소의 [Actions 실행 41630070177](https://github.com/Leegiyeon/oneul-ui-gyeol/actions/runs/41630070177)이 성공했고 Artifact를 다운로드해 보고서 3개·18개 브라우저 상태를 확인했습니다. 이전 입력은 **가상의 서버 2개 Inventory**이며 실제 온프레미스 환경을 검증한 결과가 아닙니다. [외부 실행 근거](EXTERNAL_E2E.md), [실제 저장소 감사](REAL_REPOSITORY_AUDIT.md), [공식 비용 산술 범위](OFFICIAL_COST_VALIDATION.md)를 분리해 관리합니다.

다음 순서는 **모바일 표·도면 라벨 보완 결과와 수동 시각 검토 → 공개 샘플에서 드러난 DB·API·인프라 근거 미탐 개선 → 필수 CI 검사 정책 적용 → 실제 SKU/용량 검증 확대**입니다. 회귀 테스트가 실행되는 것과 병합 전에 강제되는 것은 다릅니다. 현재 `main`은 `protected=false`, rulesets는 빈 배열이므로 required CI 차단 정책은 적용되지 않았습니다.

## MVP 완료 조건

- 대상 저장소의 Workflow 하나로 수동 **목적 선택 → 분석 → START-HERE.html 확인**.
- 온프레미스 정보 없으면 인프라 실측·DB 위치·마이그레이션 적합성을 임의 생성하지 않고 **보류**.
- 코드 관찰/명시 요구/미확인과 To-Be 설계 가정이 명확히 구분.
- 보고서는 핵심 4영역(현재 근거·권장 후보·위험/한계·다음 행동)을 중심으로, 고급 JSON/비용/QA는 선택적 확인.
- AWS 자동 배포/관리·원본 자격증명 중앙 저장 없음; 미산정 비용/용량을 0원/검증 통과로 오인하지 않음.
- 새 모드/기존 CLI·GitHub Action·4종 참조 패턴의 회귀 테스트, 한글·SVG·HTML 실제 확인을 통과해야 개발 완료.

[상세 사용자 여정과 신규 기능 우선순위](LEAN_MIGRATION_ROADMAP.md) · [제품 범위](PRODUCT.md).
