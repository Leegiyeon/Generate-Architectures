# 온프레미스 As-Is 구성 입력 (P0 · Issue #34)

**목적:** 온프레미스 서비스를 AWS로 이전하기 전에 기존 서버·DB·저장소·연결 정보를 **사용자가 확인한 범위만** 표시합니다. AWS에 접속하거나 온프레미스 서버를 진단하지 않습니다. Rehost/Replatform 및 마이그레이션 가능성 판정은 아직 제공되지 않습니다.

## 사용 방법 — 3단계

1. 대상 GitHub 저장소에서 [예제 JSON](../examples/onprem-inventory.example.json)을 복사해 `.architecture/onprem-inventory.json`에 저장합니다. 이름은 `app01`, `db01` 같은 **가상 별칭**만 사용합니다.
2. [예제 Workflow](../examples/aws-architecture.yml)를 설치했다면 Actions에서 `migrate_onprem`을 선택하고 수동 실행합니다. 기본 파일을 **자동으로 발견**하므로 추가 입력은 필요하지 않습니다. 별도의 경로는 Composite Action의 `onprem_inventory` 또는 CLI `--onprem-inventory`로 지정할 수 있습니다.
3. Artifact의 `START-HERE.html`을 열어 **As-Is 사용자 선언 구성도**와 **AWS To-Be 제안도**를 따로 비교합니다.

선택적 로컬 실행:

```bash
python3 scripts/recommend_architecture.py --repo . --output architecture-output --analysis-goal migrate_onprem
# 별도 비기밀 JSON 경로를 직접 지정하려면
python3 scripts/recommend_architecture.py --repo . --output architecture-output --analysis-goal migrate_onprem --onprem-inventory examples/onprem-inventory.example.json
```

## JSON 입력 규격 (schema_version 1.0)

필수 키는 `schema_version`, `servers`, `connections` 세 가지입니다. servers는 **1~8개**, connections는 **0~16개**입니다. 연결이 없으면 빈 배열로 입력하되 실제 서버 간 통신이 없다고 판단하지 않습니다.

```json
{
  "schema_version": "1.0",
  "servers": [
    {
      "id": "app01",
      "role": "mixed",
      "os": "linux",
      "cpu_cores": 4,
      "memory_gb": 16,
      "storage_gb": 256,
      "db_engine": "postgresql",
      "access": "internal"
    }
  ],
  "connections": []
}
```

- `role`: `application` / `database` / `proxy` / `storage` / `mixed` / `unknown`.
- `os`: `linux` / `windows` / `unknown`.
- `cpu_cores`, `memory_gb`, `storage_gb`: 0보다 큰 값 또는 `unknown`. 누락 시에도 `unknown`으로 저장.
- `db_engine`: `postgresql`, `mysql`, `mariadb`, `sqlserver`, `oracle`, `mongodb`, `other`, `none`, `unknown`. 이 값은 **사용자가 해당 서버에서 실행한다고 선언한 DB**이지 코드를 보고 할당한 것이 아닙니다.
- `access`: `internal` / `public` / `unknown`. 실제 방화벽 정책을 검증하지 않습니다.
- `integrations`: 선택 배열. `payment_api` 같은 **서비스 별칭**만 허용(실제 API 주소/고객/키 금지).
- `constraints`: 선택 배열. `downtime_sensitive`, `licensed_software`, `local_hardware`, `legacy_runtime`, `regulated_data` 중 선택.
- `connections`: 사용자 확인된 서버 간 방향성 연결만 `{"from":"app01","to":"db01","purpose":"database"}` 형태로 작성. `purpose`는 `application`, `database`, `storage`, `other` 중 하나. 없는 연결을 자동 추가하지 않습니다.

숫자·서버 역할·OS·DB 위치를 모르겠으면 **추측하지 않고** `unknown`으로 남기세요. ID는 영소문자로 시작하는 영문/숫자/`_`/`-` 24자 이하 별칭이어야 합니다. IP 주소·FQDN·포트번호·서버 실명·방화벽 ACL·로그·환경변수·자격증명은 **입력 금지**입니다. 허용되지 않은 자유 키, 중복 키, NaN/Infinity, 루트 외부 경로, 심볼릭 링크, 16KB 초과 파일은 거절합니다.

## 산출물과 신뢰 근거

- `as-is-inventory.json`: 서버/관계 `source=user_declared_unverified` 및 `provided_fields`, 저장소의 코드 탐지 단서 `source=repository_code_signal`와 미확인 질문.
- `as-is-inventory.md`: 기존 서버 표와 **사용자 선언 연결**, 코드 관측을 구분하는 설명.
- `as-is-topology.svg`: **독립적인** 온프레미스 As-Is 도면. 외부 이미지·스크립트 불포함.
- `START-HERE.html`: As-Is와 AWS To-Be를 다른 섹션에 표시. 실제 서버에 접속하지 않았음을 공통으로 안내.
- `artifact-index.json`: 추가 산출물 경로·SHA256 해시. 기존 개발자용 JSON/서비스 추천·ADR은 변경하지 않음.

**분석 범위**: 코드에 PostgreSQL 패키지가 있다는 사실은 DB가 같은 서버에 있다는 증거가 아닙니다. 사용자 선언과 코드 단서가 다르면 ‘확인 필요’ 질문으로 표시하며, 어느 쪽이 실제 환경인지 확정하지 않습니다. 미입력 필드는 운영 환경의 부재를 의미하지 않습니다.

**보안 주의**: 이 JSON은 비기밀 구조화 데이터만 의도했더라도 조직의 내부 자산 정보를 드러낼 수 있습니다. GitHub 저장소 공개 범위와 Actions Artifact 열람 권한을 확인하세요. 실제 식별자/계정/인증정보를 올리지 말고 필요하면 비공개 저장소에서 사용하세요.

**다음 단계 #35**: As-Is와 AWS To-Be의 차이, Rehost/Replatform·DB 이전·컷오버 위험을 비교하는 Migration Assessment. **현재 Inventory 사용이 AWS 이전 가능성을 인증하지 않습니다.**
