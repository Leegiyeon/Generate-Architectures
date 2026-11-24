# FastAPI PR Review — GitHub Pages 배포 준비

## 현재 상태

2026-11-24 기존 Sites 프로젝트 `appgprj_6afe374162c88191af8d2970d6884a29`는 버전 4·active로 조회됐지만 쓰기 자격 증명 발급은 다시 `404 NOT_FOUND`로 실패했습니다. 기존 공개 주소의 새 버전 배포는 미완료입니다.

대안으로 기존 공개 저장소 `Leegiyeon/Generate-Architectures`에 수동 배포 workflow를 로컬 준비했습니다. **GitHub Pages 설정 변경·원격 소스 반영·실제 배포는 아직 수행하지 않았습니다.** 공개 배포 경로를 바꾸는 운영 변경은 사용자의 확인 후 진행합니다. 진행률과 사용자 성과의 기준은 [테스트 문서](FASTAPI_PR_TEST.md#현재-목표와-진행률)를 유지합니다.

## 준비한 배포 경로

- 소스: 기존 저장소 `main`의 선택된 커밋.
- Workflow: [Publish FastAPI PR Review](../.github/workflows/fastapi-pr-pages.yml). `workflow_dispatch` 수동 실행만 허용하고 저장소·`main` 조건을 확인합니다.
- 빌드: 기존 `scripts/build_pr_preview.py`를 재사용합니다. 별도 웹 프레임워크·서버·DB·OpenAI API 키를 추가하지 않습니다.
- 배포물: 새 출력 디렉터리의 웹 자산만 업로드합니다. 전체 저장소·로컬 런처·분석 산출물을 업로드하지 않습니다. 분석 런타임은 기존 고정 SHA-256으로 검증합니다.
- 순서: 브라우저·Python 회귀 검사 → 정적 빌드 → Pages artifact 업로드 → 성공한 빌드에 의존하는 배포.
- 권한: 빌드는 소스·Pages 조회 권한, 배포는 `pages: write`·`id-token: write`만 사용합니다. 개인 액세스 토큰이나 새 Secret을 요구하지 않습니다.

GitHub 공식 문서는 공개 저장소의 GitHub Free 지원, 수동 workflow와 artifact 배포, `github-pages` 환경의 사용을 안내합니다. [커스텀 workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [게시 소스 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## 확인 후 실행할 순서

1. 검증된 앱 소스·분석기·테스트·workflow를 하나의 검토 가능한 변경으로 기존 저장소에 반영합니다. 현재 로컬의 무관한 변경을 함께 올리지 않습니다.
2. 기존 Pages 사이트·도메인·배포 이력을 먼저 확인합니다. 기존 배포가 있다면 이 앱으로 덮어쓰지 않고 사용자와 충돌을 해결합니다. Pages 상태와 실제 기본 주소는 아직 확인하지 않았습니다.
3. 충돌이 없으면 저장소 `Settings → Pages → Build and deployment → Source`를 `GitHub Actions`로 설정합니다. 저장소 관리자 또는 유지관리 권한이 필요합니다. `github-pages` 환경의 배포 대상을 `main`으로 제한합니다.
4. `main`에서 `Publish FastAPI PR Review`를 한 번 수동 실행합니다. 실패하면 해당 실행의 로그로 원인을 확인합니다.
5. 성공한 실행이 반환한 URL에서 PR·저장소 모드와 구조 비교 예제를 확인합니다. 공유 링크와 문서는 이 실제 URL을 확인한 뒤 갱신합니다. 예상 주소를 배포 완료 주소로 안내하지 않습니다.

Sites의 기존 사이트·공개 범위·프로젝트 식별자는 유지합니다. Pages가 실제로 검증되기 전에는 기존 공유 링크를 교체하지 않습니다. 이후 배포도 수동 workflow 실행으로만 이루어집니다.

## 검증 범위

로컬에서 workflow YAML·권한·작업 의존성·셸 구문과 테스트·빌드를 확인했습니다. JavaScript 63개·Python 62개 검사가 통과했고 독립 검토에서 중요한 문제는 발견되지 않았습니다. 로컬 Node는 23.11.0이며 workflow의 Node 22·Ubuntu 환경은 아직 실행하지 않았습니다.

GitHub Pages의 저장소 하위 경로를 본뜬 `/Generate-Architectures/`에서 웹 자산 27개·HTTP MIME·브라우저 Worker·Python 런타임과 실제 PR·구조 비교 예제를 확인했습니다. 공유 URL 함수의 경로 유지 검사는 통과했지만 브라우저 클립보드 복사는 권한 거부로 검증하지 못했습니다. 결과는 [테스트 문서](FASTAPI_PR_TEST.md#github-pages-배포-준비-검증--2026-11-24)에 기록했습니다. 임시 서버는 종료했습니다.

GitHub Actions 클라우드 실행, Pages 설정과 환경 보호, 실제 HTTPS 주소는 공개 배포 후 검증할 항목입니다. 로컬 준비를 공개 배포 완료로 집계하지 않습니다.
