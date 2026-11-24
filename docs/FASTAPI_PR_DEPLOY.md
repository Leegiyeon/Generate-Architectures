# FastAPI PR Review — GitHub Pages 배포

## 현재 상태

2026-11-24 사용자 승인 후 기존 공개 저장소 `Leegiyeon/Generate-Architectures`의 GitHub Pages로 전환했습니다. [공개 서비스](https://leegiyeon.github.io/Generate-Architectures/)에서 실제 PR 분석·저장소 탐색·목적별 계획·조건부 구조 비교를 확인했습니다.

- 배포 소스: `31885d77c1e5d4fcd5eded5d7a251b4d54ad130a`.
- [성공한 배포 실행](https://github.com/Leegiyeon/Generate-Architectures/actions/runs/45331752421).
- Pages 게시 방식: `workflow`, HTTPS 강제, 사용자 지정 도메인 없음.
- `github-pages` 환경: `main` 브랜치 하나만 허용. 별도 태그·다른 브랜치 배포는 허용하지 않습니다.
- 기존 Sites 사이트는 버전 4로 유지합니다. 쓰기 연결의 `404 NOT_FOUND`를 복구하지 못해 전환했으며, 기존 프로젝트·공개 범위를 바꾸거나 중복 Sites 사이트를 만들지 않았습니다.

기술 진척과 외부 사용자 성과는 [테스트 문서](FASTAPI_PR_TEST.md#현재-목표와-진행률)에서만 관리합니다. 새 공개 주소는 README·모집 문구·설정이 채워진 테스트 링크에 반영했습니다.

## 배포 방식

[Publish FastAPI PR Review](../.github/workflows/fastapi-pr-pages.yml)는 수동 `workflow_dispatch`만 실행합니다. 소스를 push하거나 PR을 올리는 것만으로는 공개 배포하지 않습니다.

1. 기존 저장소의 `main`에서 배포할 소스와 커밋을 확인합니다.
2. **Actions → Publish FastAPI PR Review → Run workflow → main**을 선택합니다.
3. JavaScript 동작과 Python 분석·패키징 회귀 검사에 이어 기존 `scripts/build_pr_preview.py`로 새 디렉터리에 빌드합니다. 실패한 빌드는 배포하지 않습니다.
4. 선언된 웹 자산 29개만 artifact로 올린 뒤 배포합니다. 저장소 전체·로컬 런처·분석 산출물은 게시하지 않습니다. 고정 Pyodide 런타임 6개 파일의 SHA-256을 확인합니다.
5. 성공한 실행이 반환한 실제 URL에서 예제와 변경 범위를 확인합니다. 이전 버전으로 돌아가야 하면 검토한 소스 복원 커밋을 `main`에 반영하고 같은 workflow로 재배포합니다. Git 이력을 강제 변경할 필요는 없습니다.

빌드는 소스·Pages 조회 권한, 배포는 `pages: write`·`id-token: write`를 사용합니다. 개인 토큰·새 Secret·서버·DB·OpenAI API 키는 필요하지 않습니다. GitHub의 [커스텀 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)와 [게시 소스 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)을 따릅니다.

## 검증 결과와 한계

Ubuntu의 Node22.23.5에서 JavaScript108개, Python3.12.16에서 관련 검사62개가 통과했습니다. 빌드·artifact·배포도 성공했습니다. 공개 HTTPS 웹 자산29개는 배포 소스와 해시가 일치하며 JS/WASM MIME·런타임6개 무결성을 확인했습니다. 같은 소스의 전체 CI도 Python294개·합성 보고서13개/화면78상태를 통과했습니다.

이번 공개 브라우저 검증에서는 저장소의 고정 SHA·루트·파일·참조 방향·사용 목적을 복사하고 새로고침 후 복원·재분석했습니다. 링크를 열 때 자동 분석하지 않으며 결과 상단에 공유·수동 복사를 제공합니다. 파일 변경 시 새 링크·이전 복사 상태 갱신과 기존 PR 링크 복원도 확인했습니다. 상세 근거는 [저장소 공유 검증 기록](FASTAPI_PR_TEST.md#저장소-분석-설정-공유--2026-11-24)을 따릅니다.

이전 P1 공개 브라우저 검증에서 PR #2144의 API 경로를 지정해 Python2/2개를 읽고, 모델 파일로 바꿔1/1개를 확인했습니다. PR·저장소 모두 분석 취소 후 입력 보존·URL 포커스·재시도를 확인했습니다. SQLModel 고정 구조 비교 예제는 재시도 후 Python2/2개·라우트2개·테이블1개입니다. 하나의90초 제한시간은 조회·Worker에 같은 AbortSignal을 전달하고, 실행 중인 Worker는 취소·시간 초과 시 종료합니다.

데스크톱1280×900·모바일390×844에서 페이지 가로 넘침이 없고 모바일 분석 취소 버튼이 화면 안에 표시됩니다. 기본 viewport를 복원했고 브라우저 오류는0건입니다. 90초 실제 대기·공개100개 초과 PR·SVG 다운로드·클립보드는 P1 검증에서 재확인하지 않았습니다. 이번 P2 검증에서는 저장소 링크의 실제 자동 복사와 수동 텍스트 일치를 확인했습니다. TimeoutError·Worker 종료·경로별 캐시·101번째 파일 선택은 자동 회귀 검사로 검증했습니다.

이전 배포에서는 커밋 미입력 시 기본 브랜치 최신 SHA 고정, 구간 이동, 공유 링크·검토 계획의 실제 클립보드 복사와 수동 복사를 확인했습니다. 제안 적용 후의 성능이나 사용자 수요는 미검증이며 GitHub 비인증 API 한도와 정적 분석 한계가 적용됩니다. 상세 근거·화면·이전 이력은 [조회 범위·취소 검증 기록](FASTAPI_PR_TEST.md#조회-범위취소-개선--2026-11-24)을 따릅니다.

## 로컬 실행

```bash
python3 scripts/build_pr_preview.py --output architecture-output/pr-preview --archive architecture-output/fastapi-pr-review-local.zip
```

ZIP을 압축 해제한 폴더에서 `python3 start.py`를 실행합니다. Windows는 `py -3 start.py`, macOS는 `START.command`도 사용할 수 있습니다. Python 3.10 이상과 GitHub 접속이 필요합니다. 런타임을 포함하며 서버는 기기의 `127.0.0.1`에서만 동작합니다. Finder 더블 클릭과 Windows 실행 자체는 별도 검증하지 않았습니다.
