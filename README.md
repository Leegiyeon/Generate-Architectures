# Generate-Architectures

**GitHub 저장소 한 번 분석 → AWS 참조 설계도와 선정 근거를 한국어로 확인하는 도구**입니다. AWS 계정이나 별도 서비스 서버 없이 시작할 수 있으며, 실제 인프라를 변경하지 않습니다.

> 현재 지원: 코드/설정의 정적 관찰 → AWS To-Be **상세 논리 설계 제안**·서비스 선정 이유·보안/운영 검토·입력 기반 비용 분석. **실제 계정 구성이나 구축 검증 결과는 아닙니다.**

## 30초 사용 안내

**1.** 대상 GitHub 저장소에 [예제 Workflow](examples/aws-architecture.yml)를 `.github/workflows/aws-architecture.yml`로 복사합니다.

**2.** 해당 저장소의 **Actions → AWS Architecture Review → Run workflow**에서 목적 하나를 선택합니다.

| 선택 | 목적 | 현재 가능한 결과 |
| --- | --- | --- |
| `new_aws` | 신규 서비스 AWS 구축 | 코드 근거를 사용한 AWS To-Be 참조 설계 및 선정 이유 |
| `migrate_onprem` | 온프레미스에서 AWS 이전 검토 | 코드 근거 기반 AWS 후보 + **현재 인프라 정보 미확인/마이그레이션 판단 보류** 안내 |

**3.** 실행 후 **Artifacts → aws-architecture-recommendation**을 다운로드하고 압축을 풀어 **`START-HERE.html`**을 엽니다. 한국어 요약은 `START-HERE.md`로도 확인할 수 있습니다.

**필수 선택은 목적 하나뿐**입니다. 로그인, AWS 계정 ID/Access Key, OpenAI API 키를 요구하지 않습니다. 코드 변경마다 설계를 자동 반복하지 않고 사용자가 요청할 때만 분석합니다.

### 무엇을 받나요?

- **AWS 설계도**: 사용 가능한 서비스와 논리 VPC/AZ·연결을 나타내는 To-Be **제안**(SVG/PNG).
- **왜 그렇게 설계했는지**: 소스에서 관찰한 단서, 선정/제외한 서비스와 검토가 필요한 조건.
- **보안·운영**: IAM, 네트워크, 확장, 관측, 백업의 검토용 항목(실제 정책 점검 아님).
- **비용·다음 행동**: 비용 입력이 없으면 **미산정**, 검증이 필요한 정보와 수동 재분석 방법.

기존 중간 JSON·다이어그램 파일 등 개발자용 결과물은 Artifact에 유지하며 처음부터 열 필요가 없습니다.

**보고서 자동 품질 검사:** 실행마다 `report-qa.json`을 생성하고 HTML 내부 링크, SVG/PNG 구조, 참조 연결, 파일 해시를 확인합니다. 이 검사는 **실제 브라우저에서의 글꼴·겹침·클리핑을 확인한 것은 아닙니다**.

별도 CI는 Chromium에서 합성 보고서 13개·78개 화면 상태를 검사합니다. 외부 저장소에서도 신규·이전 입력 없음·가상 Inventory 입력의 3경로 Actions와 다운로드 보고서 3개·18개 화면 상태를 확인했습니다. 도면 전체 수동 승인과 실제 서버·AWS 환경 검증은 남아 있습니다. [검증 범위와 실행 근거](docs/EXTERNAL_E2E.md)를 참고하세요.

### 온프레미스 이전 모드를 선택했다면

기존 서버의 구성을 직접 입력할 수 있습니다. [최소 Inventory 예시](examples/onprem-inventory.example.json)를 대상 저장소의 `.architecture/onprem-inventory.json`에 복사·수정하고 `migrate_onprem`으로 실행하면 **별도 As-Is 구성도(SVG)와 현재 구성 표**를 생성합니다. 모르는 값은 `unknown`으로 남기세요. [입력 방법과 개인정보 주의사항](docs/ONPREM_INVENTORY.md)을 참고하세요.

**Inventory는 검증되지 않은 사용자 선언**입니다. 실제 서버에 접속하지 않으며, DB 위치·네트워크·성능을 코드만으로 확인하지 않습니다. Rehost/Replatform 비교는 *검토 초안*이고 실제 이전 적합성은 미검증입니다.

`migrate_onprem`은 이전 **목적**을 기록하고, 사용자 입력 Inventory가 있다면 **선언형 As-Is 도면**도 보여줍니다. **Rehost/Replatform의 서버·선언 연결별 변경사항, 위험, 수동 전환 체크리스트를 제공하지만 최적 전략, 실제 연결 가능성 및 데이터 이전/다운타임은 검증하지 않습니다.** 입력 Inventory 및 As-Is 기능은 [#34](https://github.com/Leegiyeon/Generate-Architectures/issues/34)에서 구현했습니다. [#35 Migration Assessment](https://github.com/Leegiyeon/Generate-Architectures/issues/35)에서 사용자 선언 기반 AWS 이전 후보 비교 초안을 생성합니다. 실제 AWS 이전은 자동으로 진행하지 않습니다.

## 필요할 때만 요구사항 보완

처음에는 파일 없이 실행할 수 있습니다. 더 구체적인 설계를 원하면 [예제 요구사항 JSON](.architecture/requirements.example.json)을 참고해 대상 저장소에 `.architecture/requirements.json`을 만든 후 예제 Workflow의 `requirements_file` 주석을 해제합니다. 자격증명·개인정보·실제 서버 IP를 GitHub 저장소에 올리지 마세요.

로컬 실행(선택)은 다음과 같습니다. Graphviz와 Python 의존성을 설치해야 합니다.

```bash
python3 -m pip install -r requirements-diagrams.txt
python3 scripts/recommend_architecture.py --repo . --output architecture-output --analysis-goal new_aws
# 또는 --analysis-goal migrate_onprem
```

### 보안·신뢰성

- 보고서는 **코드에서 확인한 사실 / 사용자 입력 / 가정 / 미확인**을 구분합니다. 외부 AI와 AWS 가격 조회는 기본 비활성화입니다.
- AWS 비용·보안·성능·가용성은 실제 계정에서 검증하지 않았습니다. 근거 없는 수치·리소스·완료 판정은 만들지 않습니다.
- AWS 자동 배포, 리소스 생성·수정·삭제, 사용자 Access Key 보관은 하지 않습니다.
- 외부 저장소에서 재사용할 때 예제의 `@main`은 신뢰할 수 있는 **커밋 SHA/릴리스 태그로 고정**하는 것이 좋습니다. GitHub Actions에서 분석 코드가 저장소에 접근하는 권한도 검토하세요.

## 상세 정보(선택)

| 문서 | 필요한 경우 |
| --- | --- |
| [제품 동작/지원 범위](docs/PRODUCT.md) | 신규·온프레미스 모드 차이와 현재 한계 |
| [온프레미스 현재 구성 입력](docs/ONPREM_INVENTORY.md) | 비기밀 Inventory, As-Is 도면 |
| [AWS 이전 방식·위험 비교](docs/MIGRATION_ASSESSMENT.md) | Rehost / Replatform 변경사항과 검증 전제 |
| [간편 제품 로드맵](docs/LEAN_MIGRATION_ROADMAP.md) | 다음 개발 우선순위 |
| [사용자 보고서](docs/REPORTING.md) | HTML/산출물 확인법 |
| [외부 저장소 실행 검증](docs/EXTERNAL_E2E.md) | 3경로 Actions·Artifact·브라우저 검증과 남은 범위 |
| [실제 공개 저장소 감사](docs/REAL_REPOSITORY_AUDIT.md) | 프레임워크·API·DB·인증 탐지의 확인된 한계 |
| [요구사항·비용 입력](docs/COST_SCENARIOS.md) | 고급 요금 시나리오 |
| [공식 비용 계산 예시 검증](docs/OFFICIAL_COST_VALIDATION.md) | 공식 예시 3건의 산술 회귀, SKU·실제 견적 검증과의 차이 |
| [부하 테스트 입력](docs/CAPACITY_EVIDENCE.md) | 입력된 성능 집계값 검토 |
| [AWS 서비스 대안 비용](docs/ALTERNATIVE_COST_COMPARISON.md) | ECS/EC2/Lambda 입력 비용·운영 비교 |
| [개발자 기술 구성](docs/ARCHITECTURE.md) | 코드 파서·보안 경계·아키텍처 구성 |

**Local AWS Inspector**와 로컬 온프레미스 수집기는 아직 미구현입니다. GitHub App 서버 코드는 실제 설치·운영되는 서비스가 아니며 필수 설치 대상이 아닙니다. IaC 자동 생성/자동 배포는 제품 범위 밖입니다.
