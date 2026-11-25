# FastAPI PR Review — GitHub Pages 배포

## 현재 상태

2026-11-24 사용자 승인 후 기존 공개 저장소 `Leegiyeon/Generate-Architectures`의 GitHub Pages로 전환했습니다. [공개 서비스](https://leegiyeon.github.io/Generate-Architectures/)에서 실제 PR 분석·저장소 탐색·목적별 계획·조건부 구조 비교를 확인했습니다.

- 배포 소스: `e4d57a961920e05a979ac501e763e302790f759b` (2026-11-25 로컬 폴더 분석).
- [성공한 배포 실행](https://github.com/Leegiyeon/Generate-Architectures/actions/runs/45548482147).
- Pages 게시 방식: `workflow`, HTTPS 강제, 사용자 지정 도메인 없음.
- `github-pages` 환경: `main` 브랜치 하나만 허용. 별도 태그·다른 브랜치 배포는 허용하지 않습니다.
- 기존 Sites 사이트는 버전 4로 유지합니다. 쓰기 연결의 `404 NOT_FOUND`를 복구하지 못해 전환했으며, 기존 프로젝트·공개 범위를 바꾸거나 중복 Sites 사이트를 만들지 않았습니다.

기술 진척과 외부 사용자 성과는 [테스트 문서](FASTAPI_PR_TEST.md#현재-목표와-진행률)에서만 관리합니다. 새 공개 주소는 README·모집 문구·설정이 채워진 테스트 링크에 반영했습니다.

## 배포 방식

[Publish FastAPI PR Review](../.github/workflows/fastapi-pr-pages.yml)는 수동 `workflow_dispatch`만 실행합니다. 소스를 push하거나 PR을 올리는 것만으로는 공개 배포하지 않습니다.

1. 기존 저장소의 `main`에서 배포할 소스와 커밋을 확인합니다.
2. **Actions → Publish FastAPI PR Review → Run workflow → main**을 선택합니다.
3. JavaScript 동작과 Python 분석·패키징 회귀 검사에 이어 기존 `scripts/build_pr_preview.py`로 새 디렉터리에 빌드합니다. 실패한 빌드는 배포하지 않습니다.
4. 선언된 웹 자산33개만 artifact로 올린 뒤 배포합니다. 저장소 전체·로컬 런처·분석 산출물은 게시하지 않습니다. 고정 Pyodide 런타임 6개 파일의 SHA-256을 확인합니다.
5. 성공한 실행이 반환한 실제 URL에서 예제와 변경 범위를 확인합니다. 이전 버전으로 돌아가야 하면 검토한 소스 복원 커밋을 `main`에 반영하고 같은 workflow로 재배포합니다. Git 이력을 강제 변경할 필요는 없습니다.

빌드는 소스·Pages 조회 권한, 배포는 `pages: write`·`id-token: write`를 사용합니다. 개인 토큰·새 Secret·서버·DB·OpenAI API 키는 필요하지 않습니다. GitHub의 [커스텀 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)와 [게시 소스 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)을 따릅니다.

## 검증 결과와 한계

2026-11-25 로컬 폴더 분석 배포의 JavaScript143개·관련 Python62개와 빌드·배포가 통과했습니다. [같은 소스의 전체 CI](https://github.com/Leegiyeon/Generate-Architectures/actions/runs/45548469669)도 성공했습니다. 공개 HTTPS 자산33개·런타임6개 무결성과 JS/WASM MIME이 검증한 빌드와 일치합니다. 공개 주소에서 합성 폴더를 선택해 Python3/3개·import·라우트·테이블·조건부 후보·로컬 코드 문맥을 확인했습니다. 데스크톱1280px·모바일390×844에서 가로 넘침과 기록된 브라우저 오류·경고가 없었습니다. 민감한 실제 저장소·모든 OS/브라우저 조합·심볼릭 링크는 시험하지 않았으며 트래픽 전체를 패킷 캡처한 검증도 아닙니다. [로컬 폴더 검증 기록](FASTAPI_PR_TEST.md#private-저장소-로컬-폴더-분석--2026-11-25)을 참고하세요.

이전 시작 복구 배포 실행의 Node22 JavaScript121개·Python3.12 관련62개가 통과했습니다. 빌드·artifact·배포도 성공했습니다. 공개 HTTPS 웹 자산31개는 배포 소스와 해시가 일치하며 JPEG/JS/WASM MIME·런타임6개 무결성을 확인했습니다. [같은 소스의 전체 CI](https://github.com/Leegiyeon/Generate-Architectures/actions/runs/45533613461)도 자동 테스트와 합성 보고서13개/화면78상태를 통과했습니다.

이번 공개 브라우저 검증에서는 시작 잠금 해제·설정 복원 뒤 SALGU #7의 변경220개 중 Python40/40개와 추가 라우트7개를 확인했습니다. 폭792px 결과 화면·390×844 입력 화면에 가로 넘침이 없고 기록된 브라우저 오류·경고는 없습니다. 파일 직접 열기는 도구의 URL 정책으로 직접 조작하지 못했으며, 파일 모드·모듈 실패·기본 GET 차단·설정 복구는 자동 회귀 검사로 검증했습니다. [시작 오류 복구 검증](FASTAPI_PR_TEST.md#로컬-html-직접-열기시작-오류-복구--2026-11-25)에 기록합니다.

이전 첫 사용·공유 공개 브라우저 검증에서는 저장된 실제 PR 미리보기·입력 보존·예제 범위 초기화·취소/복구·재시도 후 Python4/4개와 결과 포커스를 확인했습니다. 데스크톱1280×900·모바일390×844에 가로 넘침이 없고 저장소 공유 설정도 복원됐습니다. 공개 검사 전 로컬 점검 시점의 원인 미확정 `animation` 오류1건을 원본 로그에 보존했으며, 이후 공개 흐름에서는 추가 오류가 없었습니다. 플랫폼별 공유 카드 노출과 실제 사용자 성과는 미검증입니다. 상세 근거는 [첫 사용·공유 공개 검증](FASTAPI_PR_TEST.md#첫-사용공유-자료-공개-검증--2026-11-24)을 따릅니다.

이전 공개 브라우저 검증에서는 실제 저장소의 Python39/39개를 읽고 연관 파일을 양방향으로 탐색했습니다. 파일 이동 후 참조 방향·목적을 유지하고 계획·공유 URL이 갱신됩니다. 자동 복사가 거부돼 URL의 읽기 전용 텍스트·전체 선택을 확인했습니다. 전체 실패 진단은 자동 회귀 검사, 빈 루트 안내는 로컬 브라우저로 검증했습니다. 데스크톱1280×900·모바일390×844에서 가로 넘침과 브라우저 오류는 없었습니다. 상세 근거는 [복구·탐색 검증 기록](FASTAPI_PR_TEST.md#저장소-실패-안내연관-파일-탐색--2026-11-24)을 따릅니다.

이전 공개 브라우저 검증에서는 저장소의 고정 SHA·루트·파일·참조 방향·사용 목적을 복사하고 새로고침 후 복원·재분석했습니다. 링크를 열 때 자동 분석하지 않으며 결과 상단에 공유·수동 복사를 제공합니다. 파일 변경 시 새 링크·이전 복사 상태 갱신과 기존 PR 링크 복원도 확인했습니다. 상세 근거는 [저장소 공유 검증 기록](FASTAPI_PR_TEST.md#저장소-분석-설정-공유--2026-11-24)을 따릅니다.

이전 P1 공개 브라우저 검증에서 PR #2144의 API 경로를 지정해 Python2/2개를 읽고, 모델 파일로 바꿔1/1개를 확인했습니다. PR·저장소 모두 분석 취소 후 입력 보존·URL 포커스·재시도를 확인했습니다. SQLModel 고정 구조 비교 예제는 재시도 후 Python2/2개·라우트2개·테이블1개입니다. 하나의90초 제한시간은 조회·Worker에 같은 AbortSignal을 전달하고, 실행 중인 Worker는 취소·시간 초과 시 종료합니다.

데스크톱1280×900·모바일390×844에서 페이지 가로 넘침이 없고 모바일 분석 취소 버튼이 화면 안에 표시됩니다. 기본 viewport를 복원했고 브라우저 오류는0건입니다. 90초 실제 대기·공개100개 초과 PR·SVG 다운로드·클립보드는 P1 검증에서 재확인하지 않았습니다. 이번 P2 검증에서는 저장소 링크의 실제 자동 복사와 수동 텍스트 일치를 확인했습니다. TimeoutError·Worker 종료·경로별 캐시·101번째 파일 선택은 자동 회귀 검사로 검증했습니다.

이전 배포에서는 커밋 미입력 시 기본 브랜치 최신 SHA 고정, 구간 이동, 공유 링크·검토 계획의 실제 클립보드 복사와 수동 복사를 확인했습니다. 제안 적용 후의 성능이나 사용자 수요는 미검증이며 GitHub 비인증 API 한도와 정적 분석 한계가 적용됩니다. 상세 근거·화면·이전 이력은 [조회 범위·취소 검증 기록](FASTAPI_PR_TEST.md#조회-범위취소-개선--2026-11-24)을 따릅니다.

## 로컬 실행

```bash
python3 scripts/build_pr_preview.py --output architecture-output/pr-preview --archive architecture-output/fastapi-pr-review-local.zip
```

ZIP을 압축 해제한 폴더에서 `python3 start.py`를 실행합니다. Windows는 `py -3 start.py`, macOS는 `START.command`도 사용할 수 있습니다. `index.html` 직접 열기는 지원하지 않습니다. 시작 실패 시 화면에서 실행 방법과 웹서비스 복구 링크를 확인할 수 있습니다. Python 3.10 이상이 필요합니다. 공개 분석만 GitHub 접속이 필요하며 로컬 폴더 분석은 선택한 Python 소스를 브라우저에서 읽습니다. 런타임을 포함하며 서버는 기기의 `127.0.0.1`에서만 동작합니다. Finder 더블 클릭과 Windows 실행 자체는 별도 검증하지 않았습니다.
