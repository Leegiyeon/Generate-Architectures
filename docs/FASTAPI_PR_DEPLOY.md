# FastAPI PR Review — GitHub Pages 배포

## 현재 상태

2026-11-24 사용자 승인 후 기존 공개 저장소 `Leegiyeon/Generate-Architectures`의 GitHub Pages로 전환했습니다. [공개 서비스](https://leegiyeon.github.io/Generate-Architectures/)에서 실제 PR 분석·저장소 탐색·목적별 계획·조건부 구조 비교를 확인했습니다.

- 배포 소스: `76593af19663cf5e317de3af06474f79302eef94`.
- [성공한 배포 실행](https://github.com/Leegiyeon/Generate-Architectures/actions/runs/45314914485).
- Pages 게시 방식: `workflow`, HTTPS 강제, 사용자 지정 도메인 없음.
- `github-pages` 환경: `main` 브랜치 하나만 허용. 별도 태그·다른 브랜치 배포는 허용하지 않습니다.
- 기존 Sites 사이트는 버전 4로 유지합니다. 쓰기 연결의 `404 NOT_FOUND`를 복구하지 못해 전환했으며, 기존 프로젝트·공개 범위를 바꾸거나 중복 Sites 사이트를 만들지 않았습니다.

기술 진척과 외부 사용자 성과는 [테스트 문서](FASTAPI_PR_TEST.md#현재-목표와-진행률)에서만 관리합니다. 새 공개 주소는 README·모집 문구·설정이 채워진 테스트 링크에 반영했습니다.

## 배포 방식

[Publish FastAPI PR Review](../.github/workflows/fastapi-pr-pages.yml)는 수동 `workflow_dispatch`만 실행합니다. 소스를 push하거나 PR을 올리는 것만으로는 공개 배포하지 않습니다.

1. 기존 저장소의 `main`에서 배포할 소스와 커밋을 확인합니다.
2. **Actions → Publish FastAPI PR Review → Run workflow → main**을 선택합니다.
3. JavaScript 동작과 Python 분석·패키징 회귀 검사에 이어 기존 `scripts/build_pr_preview.py`로 새 디렉터리에 빌드합니다. 실패한 빌드는 배포하지 않습니다.
4. 선언된 웹 자산 28개만 artifact로 올린 뒤 배포합니다. 저장소 전체·로컬 런처·분석 산출물은 게시하지 않습니다. 고정 Pyodide 런타임 6개 파일의 SHA-256을 확인합니다.
5. 성공한 실행이 반환한 실제 URL에서 예제와 변경 범위를 확인합니다. 이전 버전으로 돌아가야 하면 검토한 소스 복원 커밋을 `main`에 반영하고 같은 workflow로 재배포합니다. Git 이력을 강제 변경할 필요는 없습니다.

빌드는 소스·Pages 조회 권한, 배포는 `pages: write`·`id-token: write`를 사용합니다. 개인 토큰·새 Secret·서버·DB·OpenAI API 키는 필요하지 않습니다. GitHub의 [커스텀 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)와 [게시 소스 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)을 따릅니다.

## 검증 결과와 한계

Ubuntu의 Node 22.23.5에서 JavaScript 63개, Python 3.12.16에서 Python 62개가 통과했습니다. 빌드·artifact·배포도 성공했습니다. 공개 HTTPS의 웹 자산 27개는 배포 소스와 해시가 일치하며 JS/WASM MIME·런타임 무결성을 확인했습니다.

공개 주소의 실제 브라우저에서 #2144의 Python 4/4개·이후 구성요소 38개, SQLModel 구조 비교 예제의 Python 2/2개·라우트 2개·테이블 1개·조건부 후보 1개를 확인했습니다. 사용 목적을 테스트 계획으로 바꾸고 전제·검증·단점을 펼쳐 확인했습니다. 데스크톱 1280×900·모바일 390×844에서 페이지 가로 넘침이 없고 브라우저 오류는 0건입니다.

실제 클립보드·SVG 다운로드는 이번 공개 검증에서 재검증하지 않았습니다. 제안 적용 후의 성능이나 사용자 수요를 검증한 결과는 아닙니다. GitHub 비인증 API 한도와 정적 분석 한계가 적용됩니다. 상세 근거와 화면은 [공개 배포 검증 기록](FASTAPI_PR_TEST.md#github-pages-공개-배포-검증--2026-11-24)에 있습니다.

## 로컬 실행

```bash
python3 scripts/build_pr_preview.py --output architecture-output/pr-preview --archive architecture-output/fastapi-pr-review-local.zip
```

ZIP을 압축 해제한 폴더에서 `python3 start.py`를 실행합니다. Windows는 `py -3 start.py`, macOS는 `START.command`도 사용할 수 있습니다. Python 3.10 이상과 GitHub 접속이 필요합니다. 런타임을 포함하며 서버는 기기의 `127.0.0.1`에서만 동작합니다. Finder 더블 클릭과 Windows 실행 자체는 별도 검증하지 않았습니다.
