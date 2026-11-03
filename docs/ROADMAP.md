# Generate-Architectures — 개발 우선순위

> 기준: **사용자 시작의 단순성 → 관찰 가능한 근거 → AWS 설계/이전의 판단 가치 → 검증 가능성**.
> 과거 장문의 작업 이력은 GitHub Issue와 PR에 남아 있습니다. 이 문서는 **현재 개발 순서만** 관리합니다.

| 순서 | 우선순위 | 업무 | 상태 |
| --- | --- | --- | --- |
| 1 | P0 | [#33](https://github.com/Leegiyeon/Generate-Architectures/issues/33) 신규 AWS/온프레미스 이전 2모드 + 최초 실행 UX | 구현 후 회귀 검증 필요 |
| 2 | P0 | [#34](https://github.com/Leegiyeon/Generate-Architectures/issues/34) 최소 On-Prem Inventory + As-Is | 구현 (사용자 선언 기반) / 실브라우저 QA 대기 |
| 3 | P0 | [#35](https://github.com/Leegiyeon/Generate-Architectures/issues/35) Migration Assessment·변경사항/위험 | Rehost·Replatform 정적 초안 구현 / 실브라우저 QA 대기 |
| 4 | P0 | [#14](https://github.com/Leegiyeon/Generate-Architectures/issues/14) 단일 사용자 보고서·시각적 QA | 보고서 기반 구현, 수동 QA 필요 |
| 5 | P1 | [#16](https://github.com/Leegiyeon/Generate-Architectures/issues/16) 실제 사례 오탐·미탐/시각 QA | 합성 Golden E2E 구현 |
| 6 | P1 | [#15](https://github.com/Leegiyeon/Generate-Architectures/issues/15) 비용·용량·공식 SKU 검증 | 입력 기반 계산 구현, 실측 검증 미완료 |
| 7 | 선택 | [#36](https://github.com/Leegiyeon/Generate-Architectures/issues/36) 로컬 온프레미스 최소 진단 | 미구현 |
| 8 | 후속 | [#17](https://github.com/Leegiyeon/Generate-Architectures/issues/17) 로컬 AWS 읽기 전용 진단 | 미구현 |

별도 로컬 웹 UI([#18](https://github.com/Leegiyeon/Generate-Architectures/issues/18))와 GitHub App([#19](https://github.com/Leegiyeon/Generate-Architectures/issues/19))은 MVP에서 **보류**합니다.

## MVP 완료 조건

- 대상 저장소의 Workflow 하나로 수동 **목적 선택 → 분석 → START-HERE.html 확인**.
- 온프레미스 정보 없으면 인프라 실측·DB 위치·마이그레이션 적합성을 임의 생성하지 않고 **보류**.
- 코드 관찰/명시 요구/미확인과 To-Be 설계 가정이 명확히 구분.
- 보고서는 핵심 4영역(현재 근거·권장 후보·위험/한계·다음 행동)을 중심으로, 고급 JSON/비용/QA는 선택적 확인.
- AWS 자동 배포/관리·원본 자격증명 중앙 저장 없음; 미산정 비용/용량을 0원/검증 통과로 오인하지 않음.
- 새 모드/기존 CLI·GitHub Action·4종 참조 패턴의 회귀 테스트, 한글·SVG·HTML 실제 확인을 통과해야 개발 완료.

[상세 사용자 여정과 신규 기능 우선순위](LEAN_MIGRATION_ROADMAP.md) · [제품 범위](PRODUCT.md).
