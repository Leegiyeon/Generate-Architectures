# 실제 공개 저장소 정적 분석 감사

2026-11-03에 공식 공개 샘플 두 개를 추가로 대조했습니다. 앞선 결틈 저장소 감사는 [REPORT_QA_AUDIT.md](REPORT_QA_AUDIT.md)에 있습니다. 아래 결과는 표본별 관찰이며 정확도·성공률 또는 운영 적합성 점수가 아닙니다.

## 2026-11-04 수정 후 동일 소스 재검사

아래 최초 감사와 같은 고정 커밋을 전체 정적 보고서 파이프라인으로 다시 분석했습니다. 앱·컨테이너·DB를 실행하거나 외부 AI/AWS API를 호출하지 않았습니다.

| 대상 | 수정 후 확인 결과 | 남은 한계 |
| --- | --- | --- |
| NestJS starter | `NestJS` 기술명, AST `GET /`와 `AppController.getHello`의 `handles` 연결. 파이프라인 `api_routes=true`, 근거 `src/app.controller.ts`. 스캔/파싱 6/6, 오류 0 | DI 호출·전역 prefix·모듈 등록·실제 운영 노출 미검증 |
| FastAPI template | `FastAPI`, `Docker Compose` 표시. DB `psycopg`·`sqlmodel`, 인증 `pyjwt`의 선언 경로 `backend/pyproject.toml`. 인프라 근거 `backend/Dockerfile`·`compose.yml`. 관계형 DB 단서가 RDS 참조 후보에 반영됨 | 라이브러리 선언은 실제 DB 엔진/위치·접속·인증 실행의 증명이 아님. SQLModel 모델 노드·FastAPI prefix 합성/조건부 등록은 여전히 미지원 |

FastAPI 직접 AST 라우트 23개와 Python 3.12에서 읽지 못한 3.14 구문 오류 한 개는 그대로입니다. 해당 보고서의 근거 계약은 `partial`로 남습니다. NestJS의 동적·배열·옵션 경로는 평가하지 않고 `unresolved_routes`에 파일/행과 고정 이유를 기록하며, 이런 미해결 경로가 있으면 근거 계약도 `partial`입니다.

의존성 관찰과 DB/인증/잡 신호의 `source_paths`에는 패키지명 대신 실제 선언 파일 경로를 연결했습니다. API 단서에도 AST 근거 파일 경로를 연결합니다. 원본 의존성 URL·환경 marker를 실행/조회하거나 보고서로 복사하지 않습니다. Python 지원 형식과 NestJS 한계는 [ARCHITECTURE.md](ARCHITECTURE.md)에 명시합니다.

두 실제 샘플에서 생성한 보고서는 Chrome 1440/390/320px × 상세 닫힘/펼침의 12개 화면 상태를 통과했습니다. 자동 렌더링 검사이며 사람의 시각 승인이나 실제 서비스 검증은 아닙니다.

이하 수치와 미탐 표는 **2026-11-03의 수정 전 감사**로 보존합니다.

## 범위와 재현 조건

- 공개 저장소를 별도 폴더에 얕게 복제하고 고정 커밋의 설정·소스 파일을 직접 읽었습니다.
- `inspect_repository`와 `build_application_graph`를 실행했습니다. 대상 프로젝트의 의존성 설치, 앱 실행, 테스트 실행, Docker 실행, DB 연결, AWS 접근 및 유료 AI 호출은 하지 않았습니다.
- 분석 도구의 기존 Python 3.12.16 환경과 기존 Babel 파서를 사용했습니다. 테스트/fixture 경로를 두 분석기가 함께 제외하는 이번 수정 상태를 대상으로 합니다.
- 저장소 파일 개수와 AST 파일 개수는 탐색 목적·제외 규칙이 달라 서로 같지 않습니다. `scan_truncated=false`도 모든 언어 기능을 지원한다는 의미는 아닙니다.

| 대상 | 고정 커밋 | 저장소 탐색 | AST 스캔/파싱 | 상한 잘림 | 파싱 오류 |
| --- | --- | --- | --- | --- | --- |
| [nestjs/typescript-starter](https://github.com/nestjs/typescript-starter/tree/da4aab8ea68d69b1974391958cf0f7ffd104be22) | `da4aab8ea68d69b1974391958cf0f7ffd104be22` | 18개 | 6/6개 | 두 분석기 모두 false | 0개 |
| [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template/tree/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4) | `9c81b46ff7e250fffdbfa1b258746c849f9bcbb4` | 223개 | 125/124개 | 두 분석기 모두 false | 1개 |

동일한 체크아웃에서 다음처럼 재검사할 수 있습니다. 대상 소스는 실행하지 않습니다.

```python
from scripts.repository_analyzer import inspect_repository
from scripts.application_graph import build_application_graph

profile = inspect_repository("/path/to/pinned-checkout")
graph = build_application_graph("/path/to/pinned-checkout")
print(profile)
print(graph["scanned_source_files"], graph["parsed_source_files"], graph["errors"])
```

## NestJS TypeScript starter

### 파일에서 확인한 사실

- [package.json:23](https://github.com/nestjs/typescript-starter/blob/da4aab8ea68d69b1974391958cf0f7ffd104be22/package.json#L23): `@nestjs/common`, `@nestjs/core`, `@nestjs/platform-express`를 선언합니다.
- [src/main.ts:4](https://github.com/nestjs/typescript-starter/blob/da4aab8ea68d69b1974391958cf0f7ffd104be22/src/main.ts#L4): `NestFactory.create`와 `app.listen`이 있습니다.
- [src/app.controller.ts:4](https://github.com/nestjs/typescript-starter/blob/da4aab8ea68d69b1974391958cf0f7ffd104be22/src/app.controller.ts#L4): `@Controller()` 및 `@Get()`의 `getHello`가 서비스 메서드를 호출합니다.
- [src/app.service.ts:3](https://github.com/nestjs/typescript-starter/blob/da4aab8ea68d69b1974391958cf0f7ffd104be22/src/app.service.ts#L3): `@Injectable()` 서비스가 문자열을 반환합니다.
- 체크아웃의 선언 의존성·주요 앱 소스에서는 DB·인증 구현이나 Docker/Compose 구성을 확인하지 못했습니다. 운영 환경에서 이 기능이 없다는 증명으로 사용하지 않습니다.

### 현재 결과와 미탐

| 항목 | 분석 결과 | 대조 결과 |
| --- | --- | --- |
| 프레임워크 | 기술 목록 `Node.js` | NestJS 프레임워크 이름은 미탐 |
| API | `signals.api_routes=false`, 경로 근거 0개, AST route 0개 | 실제 `@Get()` 핸들러를 놓침 |
| AST | module 6개, function 4개, errors 0개 | 파싱 성공이 NestJS 데코레이터·DI 의미 분석 성공을 뜻하지 않음 |
| DB / 인증 / Docker | 각 signal false | 이번에 읽은 소스와 선언에서는 추가 단서를 찾지 못했으며 부재 확정은 하지 않음 |
| 정적 배포 후보 | `static_candidate=false` | API 미탐에도 정적 배포로 확정하지 않음 |
| 기본 제안 | `containers`, workload `web` | 실행 가능한 배포 검증 결과가 아닌 기존 참조 패턴 |

NestJS 데코레이터 라우팅과 DI 연결은 현재 AST 지원 범위 밖입니다. API가 없는 앱으로 소개하거나 “서버 불필요”로 해석하면 안 됩니다. 테스트의 `app.controller.spec.ts`와 `test/`는 분석 소스에서 제외됐습니다.

## Full Stack FastAPI template

### 파일에서 확인한 사실

- [backend/pyproject.toml:5](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/pyproject.toml#L5): Python `>=3.14`, FastAPI, Alembic, `psycopg[binary]`, SQLModel, PyJWT 및 pwdlib 의존성을 선언합니다.
- [backend/app/main.py:21](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/main.py#L21): FastAPI 앱 생성, API router 연결 및 프런트엔드 제공 구문이 있습니다.
- [backend/app/core/db.py:7](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/core/db.py#L7): SQLModel 엔진을 생성합니다. [compose.yml:20](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/compose.yml#L20)은 PostgreSQL 컨테이너를 선언하고, 같은 파일 64행에 DB 연결 문자열 템플릿이 있습니다. 실제 접속은 확인하지 않았습니다.
- [backend/app/models.py:51](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/models.py#L51) 및 87행: `table=True`인 User와 Item SQLModel 테이블이 있습니다.
- [backend/app/core/security.py:22](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/core/security.py#L22): JWT 생성 및 비밀번호 검증 코드가 있습니다. [backend/app/api/deps.py:16](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/api/deps.py#L16)에 OAuth2 토큰 의존성과 사용자 검증이 있습니다. 보안 정책의 적절성은 평가하지 않았습니다.
- [backend/Dockerfile:19](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/Dockerfile#L19)는 Python 이미지 및 65행의 FastAPI 실행 명령을 선언합니다. [frontend/vite.config.ts:8](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/frontend/vite.config.ts#L8)는 Vite 빌드 설정입니다.

### 현재 결과와 미탐

| 항목 | 분석 결과 | 대조 결과 |
| --- | --- | --- |
| 프레임워크 | `Docker`, `Node.js`, `Python`, `Vite` | FastAPI 자체 이름은 미탐 |
| API | metadata signal true, 경로 근거 9개; AST route 23개 | 서버 단서를 탐지. 경로 근거 개수와 endpoint 개수는 별도 |
| DB | relational/document signal false, DB 경로·의존성 근거 빈 배열, AST model 0개 | SQLModel·psycopg/PostgreSQL 및 테이블 정의 미탐 |
| 인증 | `authentication_library=false`, 인증 의존성 빈 배열 | Python 의존성·자체 JWT 흐름 미탐. 인증 없음이 아닌 미확인으로 유지 |
| 컨테이너 | `docker=true`, manifest에 `backend/Dockerfile` | 컨테이너 단서 자체는 탐지 |
| 인프라 경로 | `infrastructure_paths=[]`; `compose.yml` manifest 없음 | 중첩 Dockerfile 경로 및 Compose `.yml` 명칭 미탐 |
| 정적 배포 후보·제안 | `static_candidate=false`, 기본 `containers` 제안 | API/컨테이너 단서로 정적 배포 확정은 피함. DB 미탐으로 기본 제안에 RDS 노드는 없음 |

API 파일 근거 9개에는 `__init__.py` 두 개, `deps.py`, `main.py`도 포함됩니다. 이 네 파일에는 직접 라우트 데코레이터가 없습니다. 경로 기반 서버 단서로는 사용할 수 있지만 실제 endpoint 네 개로 계산하면 오탐입니다. 테스트 디렉터리는 두 분석기에서 제외됐습니다.

직접 확인한 데코레이터 수와 AST route 수는 다음과 같습니다. 이 표의 일치는 현재 대상 파일의 구문 비교에 한정됩니다.

| 라우트 파일 | 직접 데코레이터 / AST route |
| --- | --- |
| `items.py` | 5 / 5 |
| `login.py` | 5 / 5 |
| `private.py` | 1 / 1 |
| `users.py` | 10 / 10 |
| `utils.py` | 2 / 2 |

라우트의 실제 배포 URL·활성화 조건은 검증하지 않았습니다. 예를 들어 [items.py:10](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/api/routes/items.py#L10)의 `/items` prefix와 `main.py`의 `settings.API_V1_STR`은 합성하지 않으며, [api/main.py:13](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/api/main.py#L13)의 development 조건부 private router도 정적 route 목록에 포함됩니다.

AST 오류 한 개는 [deps.py:36](https://github.com/fastapi/full-stack-fastapi-template/blob/9c81b46ff7e250fffdbfa1b258746c849f9bcbb4/backend/app/api/deps.py#L36)의 괄호 없는 다중 예외 구문을 Python 3.12 파서가 읽지 못한 `SyntaxError`입니다. 대상은 Python 3.14를 요구하므로 대상 코드가 잘못됐다는 판정이 아닙니다. 오류를 기록하고 나머지 124개 파일을 계속 분석했습니다. 이 파일에 포함된 인증 의존성·검증 흐름의 AST 연결은 누락됩니다.

## 후속 개선 우선순위

1. Python 의존성 파일의 제한된 정적 파싱으로 DB·프레임워크 단서를 수집하고, SQLModel 등 지원 범위를 명시합니다. DB 미탐이 설계 근거 누락으로 이어지는 사례를 회귀로 고정합니다.
2. 중첩 Dockerfile과 일반적인 Compose 파일 이름을 manifest/근거 경로에 일관되게 기록합니다.
3. NestJS 데코레이터를 지원하기 전에는 API 미탐 가능성을 분명히 유지합니다. 지원할 때는 import 근거·controller prefix·handler 연결을 검증하는 별도 회귀가 필요합니다.
4. 분석기 Python 버전보다 새로운 구문을 만났을 때의 부분 분석 상태와 영향 파일을 보고서에서 명확히 표시합니다.
5. 라우트 구문, prefix 합성, 조건부 등록, 실제 운영 노출은 별도 검증 범위로 유지합니다.

표본 두 개로 제품 전체의 탐지 정확도나 보안성을 일반화하지 않습니다. 외부 사용자 저장소의 GitHub Actions 전체 흐름 검증, 앱 런타임 및 AWS 실환경 검증은 이 감사에서 수행하지 않았습니다.
