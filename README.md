# Generate-Architectures

무료 [FastAPI PR 리뷰 웹 체험](https://leegiyeon.github.io/Generate-Architectures/)과 GitHub 저장소의 AWS 참조 설계 도구입니다. 현재 개발은 PR 변경·코드 구조 시각화에 집중하며, GitHub App과 AWS 도구 확장은 보류합니다. 로그인이나 OpenAI API 키 없이 시작할 수 있습니다.

## FastAPI PR 리뷰 체험 (실험)

웹에서 `FastAPI 예제로 시작` 또는 공개 PR 링크를 입력하세요. 전체·API·DB 관점과 경로·모델 범위를 선택하면 라우트·핸들러·직접 선언한 모델 필드·마이그레이션 변경을 코드 근거와 함께 비교합니다. PR 이전·이후의 파일→라우트·모델 구조도와 SVG, 검토 제안을 제공합니다.

`저장소 현재 구조`에서는 공개 저장소 URL·40자리 커밋 SHA·Python 소스 루트로 직접 import·라우트·테이블 선언을 탐색합니다. 파일과 사용 목적(온보딩·변경 검토·테스트 계획)에 따라 확인 순서·다음 행동·완료 조건을 제공합니다. `구조 비교 예제`로 현재 구조와 조건부 개선 후보를 확인할 수 있습니다. 후보는 같은 파일의 라우트·테이블 역할 분리와 직접 import 순환 조정 두 규칙이며, 전제·검증·단점을 함께 표시합니다. 제안의 적용이나 개선 효과를 검증한 결과는 아닙니다.

분석은 브라우저 안에서 수행하며 대상 소스는 실행하지 않습니다. GitHub 비인증 조회 한도가 적용됩니다. 저장소 원본은 최대100개·파일당64KiB, 화면은 파일80개·관계400개로 제한하며 생략·미확인을 알립니다. 실제 호출·DB 접근·운영 인프라, 상속·동적 등록의 영향은 수동 확인해야 합니다.

`분석 설정 링크 복사`는 PR·관점·범위를 공유합니다. 링크를 열고 ‘변경 확인’을 누르는 시점의 PR을 읽으며 고정된 결과를 공유하지 않습니다. 검토 계획과 비교 후보는 코드 근거를 포함한 텍스트로 확인할 수 있습니다.

[설정이 채워진 테스트 링크·검증 기록](docs/FASTAPI_PR_TEST.md) · [코드 구조·분석 한계](docs/PR_CODE_STRUCTURE.md) · [GitHub Pages 배포·로컬 실행](docs/FASTAPI_PR_DEPLOY.md)

### 로컬 실행

웹 자산과 Python 3.10 이상에서 실행할 ZIP을 만듭니다. 첫 빌드는 고정 Pyodide 런타임을 공식 배포처에서 받고 SHA-256을 확인합니다.

```bash
python3 scripts/build_pr_preview.py --output architecture-output/pr-preview --archive architecture-output/fastapi-pr-review-local.zip
```

ZIP 전체를 풀고 `fastapi-pr-review` 폴더에서 `python3 start.py`(Windows: `py -3 start.py`)를 실행하세요. macOS에서는 `START.command`도 사용할 수 있습니다. 서버는 `127.0.0.1`의 빈 포트로 열리며 Ctrl+C로 종료합니다. 공개 GitHub 조회에는 인터넷이 필요합니다. ZIP은 웹 출력 폴더 밖에 지정하세요.

이미 받은 Git 저장소도 대상 코드를 실행하지 않고 비교합니다.

```bash
python3 scripts/preview_fastapi_pr.py --repo /path/to/checkout --base BASE_SHA --head HEAD_SHA
```

열린 PR의 `BASE_SHA`에는 기준·PR 브랜치의 공통 조상을, `HEAD_SHA`에는 PR 커밋을 지정합니다. `--focus api|db|all`, `--path`, `--model src/orm.py:Account`, `--response-model`로 범위를 바꿀 수 있습니다. Python 3.10 이상과 Git이 필요하며 대상 문법을 지원하는 Python을 사용하세요.

## 30초 사용 안내

기존 AWS 참조 설계 도구는 실제 인프라를 변경하지 않습니다.

> 현재 지원: 코드/설정의 정적 관찰 → AWS To-Be **상세 논리 설계 제안**·서비스 선정 이유·보안/운영 검토·입력 기반 비용 분석. **실제 계정 구성이나 구축 검증 결과는 아닙니다.**

1. 대상 저장소에 [예제 Workflow](examples/aws-architecture.yml)를 `.github/workflows/aws-architecture.yml`로 복사합니다.
2. **Actions → AWS Architecture Review → Run workflow**에서 목적 하나를 선택합니다.
3. **Artifacts → aws-architecture-recommendation**을 내려받아 압축을 풀고 **`START-HERE.html`**을 엽니다. 한국어 요약은 `START-HERE.md`에도 있습니다.

| 목적 | 결과 |
| --- | --- |
| `new_aws` 신규 서비스 AWS 구축 | 코드 근거에 따른 AWS To-Be 참조 설계·선정 이유 |
| `migrate_onprem` 온프레미스 이전 검토 | AWS 후보와 현재 인프라 미확인·판단 보류 안내 |

필수 선택은 목적 하나이며 AWS 계정 ID·Access Key·OpenAI API 키가 필요하지 않습니다. 분석은 수동 실행하고 push·PR에서는 테스트만 수행합니다. 설계도(SVG/PNG), 코드 근거·가정, 보안·운영 검토 항목과 다음 행동을 제공합니다. 비용 입력이 없으면 **미산정**입니다.

온프레미스 모드에서는 [최소 Inventory 예시](examples/onprem-inventory.example.json)를 `.architecture/onprem-inventory.json`에 복사해 현재 구성을 입력할 수 있습니다. 모르는 값은 `unknown`으로 남기세요. **검증되지 않은 사용자 선언**으로 As-Is 도면과 Rehost/Replatform 비교 초안을 만들며, 실제 서버 연결·데이터 이전·다운타임·최적 전략은 검증하지 않습니다. [입력 안내](docs/ONPREM_INVENTORY.md), [이전 후보 비교](docs/MIGRATION_ASSESSMENT.md)를 참고하세요.

더 구체적인 요구사항은 [예제 JSON](.architecture/requirements.example.json)을 `.architecture/requirements.json`으로 복사한 뒤 Workflow의 `requirements_file` 주석을 해제합니다. 자격증명·개인정보·실제 서버 IP를 저장소에 올리지 마세요.

로컬 AWS 분석에는 Python 3.11 이상(권장 3.14), Graphviz와 Python 의존성이 필요합니다.

```bash
python3 -m pip install -r requirements-diagrams.txt
python3 scripts/recommend_architecture.py --repo . --output architecture-output --analysis-goal new_aws
```

보고서 품질 검사는 링크·SVG/PNG 구조·참조·해시를 확인하고 별도 CI는 Chromium에서 합성 보고서를 검사합니다. 실제 AWS 비용·보안·성능·가용성과 도면 전체 수동 승인은 미검증입니다. [외부 실행·브라우저 검증 범위](docs/EXTERNAL_E2E.md)를 참고하세요.

## 보안과 상세 정보

코드에서 확인한 사실·사용자 입력·가정·미확인을 구분합니다. 외부 AI·AWS 가격 조회는 기본 비활성화이며 AWS 자동 배포·Access Key 보관을 하지 않습니다. 다른 저장소에서 Action을 사용할 때는 신뢰할 커밋 SHA/릴리스 태그로 고정하고 실행 권한을 검토하세요.

**Local AWS Inspector**와 로컬 온프레미스 수집기는 미구현입니다. GitHub App 서버 코드는 실제 설치·운영 서비스가 아니며 필수 설치 대상이 아닙니다. IaC 자동 생성·자동 배포는 제품 범위 밖입니다.

[제품·지원 범위](docs/PRODUCT.md) · [현재 로드맵](docs/ROADMAP.md) · [사용자 보고서](docs/REPORTING.md) · [개발자 구성](docs/ARCHITECTURE.md) · [실제 저장소 감사](docs/REAL_REPOSITORY_AUDIT.md) · [요구사항·비용 입력](docs/COST_SCENARIOS.md) · [비용 예시 검증](docs/OFFICIAL_COST_VALIDATION.md) · [부하 시험 입력](docs/CAPACITY_EVIDENCE.md) · [AWS 대안 비용](docs/ALTERNATIVE_COST_COMPARISON.md)
