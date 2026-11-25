# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-11-25
- Primary product surfaces: FastAPI PR Review의 공개 PR 비교·공개 저장소 및 로컬 폴더의 현재 구조 입력·결과·코드 구조도.
- Evidence reviewed: `app/pr_preview/{index.html,app.js,styles.css}`, `scripts/{pr_preview_browser.py,preview_fastapi_pr.py,application_graph.py,render_application_graph.py}`, `docs/{PRODUCT.md,FASTAPI_PR_TEST.md}`.

## Brand
- Personality: 간결하고 근거를 확인할 수 있는 개발 도구.
- Trust signals: 커밋·파일·행 링크, 읽은 범위와 미확인 범위 표시.
- Avoid: 운영 환경을 관찰한 것처럼 표현, 근거 없는 구성요소·연결 생성.

## Product goals
- Goals: PR의 변경과 관련 코드 구조를 함께 이해하고, 고정 커밋의 Python 파일 import·직접 선언으로 현재 구조를 살펴본다. 저장소 모드에서는 온보딩·변경 검토·테스트 계획 목적에 따라 같은 근거의 읽기 순서·확인 행동·완료 조건을 제공한다. 같은 파일의 라우트·테이블 공존과 선택 파일의 직접 import 순환에 한해 현재 구조와 조건부 개선 후보를 비교한다.
- Non-goals: 모든 언어·파일의 완전한 저장소 분석, 실제 호출·최종 라우터 등록·실제 서버·AWS 인프라 자동 진단.
- Success signals: 실제 공개 PR의 선언과 도표·소스 링크가 일치. 사용자 실사용·재사용은 별도 미검증.
- First-use goal (2026-11-24): 분석을 기다리기 전에 실제 공개 PR의 저장된 변경 근거를 확인하고, 예제의 최신 재분석 또는 본인 PR 입력으로 이어간다. 무료·로그인/설치/API 키 불필요·공개 Python 범위를 첫 화면에 명시한다. 사용자 초대 문구·공유 이미지를 준비하되 실제 유입·재사용 성과와 구분한다.

## Personas and jobs
- Primary personas: FastAPI API·DB 변경을 검토하는 개발자.
- User jobs: 구조 파악, 변경 전후 비교, 원본 확인, 다이어그램 공유.
- Key contexts of use: 공개 PR 리뷰와 프로젝트 온보딩.

## Information architecture
- Primary navigation: 한 페이지에서 PR 변경 분석 / 저장소 현재 구조 / 로컬 폴더 분석을 선택. 전환 시 이전 결과 DOM을 비운다. 로컬 폴더는 사용자가 clone하거나 압축 해제한 프로젝트를 native 폴더 입력으로 선택하고 Python 소스 루트를 지정한 뒤 명시적으로 분석한다. GitHub 인증·업로드 서버는 추가하지 않는다.
- Core routes/screens: PR 입력 → 결과 시작·복사·바로가기 → 전후 구조 → 검토 제안 → 변경 근거. 저장소 URL·선택 커밋·소스 루트 → 파일·참조 방향·사용 목적 선택 → import 도표·개선 후보 비교·목적별 검토 계획·근거·직접 선언. 결과 상단의 분석 설정 공유는 저장소·분석한 전체 SHA·소스 루트·선택 파일·참조 방향·사용 목적을 URL fragment에 담는다. 링크를 열면 저장소 모드와 입력을 복원하며 분석은 사용자가 시작한다. 커밋을 생략하면 기본 브랜치 최신 커밋을 한 번 조회해 전체 SHA로 고정한다. 명시한 SHA는 임의 대체하지 않는다. 개선 후보는 별도 펼침 영역에서 선택하며 해당 파일의 관찰 근거가 있을 때만 제시한다.
- Content hierarchy: 분석 범위·커밋, 도표, 구조 기반 확인 항목, 상세 변경 근거.
- First-use hierarchy: 대상과 얻는 결과 → 무료 체험 조건 → 입력 및 ‘저장된 결과 먼저 보기’ → 저장 시점·고정 커밋·원본 행이 있는 실제 PR 발췌 → 최신 예제 분석/내 PR 입력. 미리보기는 네트워크·Worker 없이 열고, 현재 분석 결과와 별도 영역으로 구분한다. 분석 시작 또는 모드 전환 시 닫고 분석 중에는 열지 않는다. 기존 입력·관점·범위는 미리보기 열기/닫기로 변경하지 않는다.

## Design principles
- 관찰된 선언과 관계만 연결한다. 파일이 라우트·모델을 선언한다는 연결은 호출·DB 접근과 구분한다.
- 모든 도표 구성요소는 같은 스냅샷의 코드 근거로 이동할 수 있다.
- 저장소 관계의 코드 근거는 도표 바로 아래에서 이웃 파일별로 묶는다. ‘이 파일 구조 보기’는 기존 파일 선택을 바꾸고 참조 방향·목적을 유지한다. 원본 코드 링크와 SVG의 고정 커밋 링크는 계속 제공한다.
- Tradeoffs: PR은 기존 조회만 재사용. 저장소 모드는 메타데이터·커밋·tree 3회와 최대100개 원본 조회를 추가하고 한도를 표시한다. 유료 API·새 서버는 추가하지 않는다.

## Visual language
- Color: 기존 파란색·회색 토큰 재사용. 상태는 색상과 문구 함께 표시.
- Typography: 기존 시스템 글꼴, 도표 본문 14px 이상.
- Spacing/layout rhythm: 기존 결과 카드 간격·테두리 재사용.
- Shape/radius/elevation: 기존 카드와 동일한 작은 라운드, 그림자 추가 최소화.
- Motion: 애니메이션 없이 전후 즉시 전환.
- Imagery/iconography: 근거가 있는 코드 구조도만 사용.
- Distribution: 대표 이미지는 기존 색상·타이포·실제 예제의 변경 항목으로 구성한 정적 카드로 만든다. OG/Twitter/canonical은 배포 경로를 포함한 절대 HTTPS URL을 사용한다. 사용자 수·시간 절감·완전한 시스템 아키텍처 분석을 주장하지 않는다.

## Components
- Existing components to reuse: 결과 섹션, source-link, coverage-note, report-actions, copy-output. PR·저장소 설정 링크에 공용 복사 상태·읽기 전용 수동 복사를 재사용한다.
- New/changed components: 이전/이후 전환 버튼, SVG 구조도, 접근 가능한 구성요소 목록, SVG 다운로드, 구조 기반 검토 제안. 저장소 목적 선택은 native select, 검토 계획은 기존 result-section·evidence-item·source-link를 재사용하고 복사 버튼으로 커밋·범위·근거·한도를 함께 전달한다. 개선 후보의 현재·제안 도표는 동일한 SVG·가로 스크롤·저장 helper를 재사용한다. 제안 역할·관계는 점선과 ‘가정’ 문구를 함께 쓰며 가짜 파일 경로·소스 링크는 만들지 않는다.
- Variants and states: 선언 추가·수정·삭제·동일, 미확인·표시 한도.
- Token/component ownership: `app/pr_preview/styles.css`, `app/pr_preview/{architecture,repository-view}.js`. SVG 저장은 공통 helper를 사용한다.

## Accessibility
- Target standard: WCAG 2.2 AA를 목표로 기존 키보드·텍스트 패턴 유지. 정식 적합성 인증은 미실시.
- Keyboard/focus behavior: 전환·다운로드는 일반 버튼, 코드 근거는 링크. 새 분석 성공 시 결과 시작으로 포커스와 스크롤을 옮긴다. 관점·파일·목적 전환은 불필요하게 화면 위치를 초기화하지 않는다. PR 결과 상단에서 API·DB·변경 파일과 입력 수정으로 바로 이동할 수 있다. SVG와 별도로 HTML 구성요소 목록 제공.
- 연관 파일 구조 보기 버튼은 파일 선택창으로 포커스와 스크롤을 옮겨 새 도표를 이어 읽게 한다. 같은 이웃을 향한 여러 import 근거는 보존하되 탐색 버튼은 하나만 제공한다.
- Contrast/readability: 상태 문구·범례 병기, 긴 경로 줄바꿈.
- Screen-reader semantics: SVG title/description, 도표와 동일한 구성요소 목록.
- Reduced motion and sensory considerations: 도표에 움직임 없음.

## Responsive behavior
- Supported breakpoints/devices: 기존 700px/420px, 최소 390px 검증.
- Layout adaptations: 도표 영역만 가로 스크롤, 페이지 가로 넘침 없음. 설명·목록은 화면 폭에 맞춤.
- Touch/hover differences: 핵심 정보는 hover에 의존하지 않는다.

## Interaction states
- Local selection: 폴더를 선택한 뒤에만 분석·선택 해제를 활성화한다. 새 선택·루트 변경·선택 해제는 이전 결과를 비우고, 선택 해제는 FileList도 해제한다. 빈 선택·미지원 브라우저·Python 없음·모든 파일 실패를 구분한다. 모드 전환은 분석하지 않으며 로컬 경로나 소스를 URL·피드백·스토리지에 기록하지 않는다. `#mode=local`은 입력 없는 진입 링크만 지원한다.
- Local evidence: 선택 시점의 파일·상대경로·행·읽기 전용 코드 문맥으로 근거를 표시한다. Git 커밋을 추정하지 않는다. 로컬 SVG에는 외부 소스 링크를 넣지 않으며 설정 공유 링크를 만들지 않는다. 기존 파일/참조 방향/목적별 계획·조건부 후보를 재사용한다. 복사·SVG 저장에는 파일명과 선언 정보가 포함됨을 알린다.
- Local privacy: 선택한 Python 원본은 같은 브라우저 Worker로만 전달하며 업로드·GitHub 요청·영구 저장·소스 실행을 하지 않는다. 로컬 분석 성공 후에도 Worker를 종료해 런타임을 유지하지 않는다. 첫 웹 분석에서는 분석기 정적 자산 다운로드가 필요하다. 폴더 선택 API는 브라우저 지원을 확인하고 미지원이면 데스크톱 브라우저 사용 방법을 안내한다.
- Startup failure: HTML의 분석 입력·버튼은 기본 잠금 상태이며 전체 모듈 초기화가 끝난 뒤 해제한다. 모듈과 독립적인 classic 시작 스크립트가 file:// 직접 열기·모듈 읽기/초기화 실패·JavaScript 비활성화를 안내한다. 준비 전 기본 폼 GET 제출을 막아 입력이 query로 바뀌며 무반응처럼 보이지 않게 한다. 파일 모드에서는 모듈을 요청하지 않으며 자동 외부 이동 없이 배포 서비스 링크와 ZIP의 START.command/start.py 실행 방법을 제공한다.
- Startup recovery: 고정된 canonical 배포 주소의 fragment에 알려진 PR·범위 또는 공유 설정만 전달한다. 로컬 파일 경로·알 수 없는 query 값·토큰은 복구 링크로 복사하지 않는다. 기존 공유 설정 검증기를 목적지에서 사용하고 자동 분석하지 않는다. 저장된 예제는 시작 실패 상태에서도 읽을 수 있다.
- Loading: 조회·분석 중 양쪽 입력과 모드 전환을 잠그고 진행 상태·취소 버튼으로 이동한다. 취소 버튼은 활성 상태를 유지하며 사용자 취소 후 입력을 보존하고 해당 입력으로 돌아간다. 조회부터 Worker 분석까지 하나의 90초 제한시간을 사용하고, 취소·시간 초과는 원본 조회와 Worker를 중단한다. 저장소 고정 스냅샷은 2건·3분 캐시.
- Empty: 인식된 선언이 없거나 소스를 읽지 못한 범위를 구별해 표시. 개선 후보가 없으면 지원 규칙·표시 범위에서 후보를 찾지 못한 상태로 알린다. 구조가 적절하다거나 개선이 불필요하다는 판정으로 바꾸지 않는다.
- 저장소 파일이 하나도 표시되지 않아도 HTTP·인코딩·구문 오류의 구체적 진단을 생략하지 않는다. 이때 진단 목록은 펼쳐 두며, 소스 루트에 Python 파일이 없는 상태와 읽기·해석에 실패한 상태를 다른 문구로 안내한다.
- Error: 공유 링크의 중복·혼합·알 수 없는 항목, 잘못된 커밋·루트·파일은 부분 적용하지 않고 오류 패널에 표시한다. 공유된 파일이 읽기·표시 범위에 없으면 기본 파일로 열었음을 명시한다. 기존 오류 패널. 구조도 미지원은 전체 분석 실패로 취급하지 않는다.
- Success: 저장소 공유 링크는 최신 브랜치 대신 실제 분석한 고정 SHA를 사용한다. 선택 파일·참조 방향·사용 목적 변경 시 공유 출력과 이전 복사 상태를 갱신한다. 입력·예제를 바꾸면 이전 공유 링크의 파일·목적을 새 저장소에 적용하지 않는다. 기본은 이후 구조, 이전 구조 전환과 SVG 저장 지원. 저장소는 온보딩을 기본으로 하며 목적·파일을 바꾸면 현재 스냅샷에서 즉시 검토 계획을 갱신한다. 도표 참조 방향과 사용 목적은 독립적으로 유지한다. 모든 복사 성공·실패는 해당 버튼 옆 live status로 알린다. 수동 복사 내용은 언제든 읽기 전용 텍스트로 펼칠 수 있고, 자동 복사가 거부되면 같은 내용을 펼쳐 선택한다. 새 분석·관점·계획 전환에서는 이전 복사 상태를 남기지 않는다.
- Disabled: 분석 중 기존 입력 잠금 유지.
- Offline/slow network: 취소는 오류 경고와 구별해 알린다. 시간 초과는 경로·소스 루트를 좁히거나 네트워크를 확인한 뒤 재시도하도록 안내한다. 중단한 작업의 늦은 응답을 새 결과로 표시하지 않는다.

## Content voice
- Tone: 짧고 직접적인 한국어.
- Terminology: ‘PR 관련 코드 구조’, ‘선언 관계’, ‘검토 제안’. 운영 시스템 전체라고 부르지 않는다.
- Microcopy rules: 제안마다 관찰 근거와 확인할 행동을 표시. 목적별 계획에는 현재 확인·다음 행동·완료 조건·코드 근거를 구분한다. 파일 수와 import 관계 수, 표시한 선언과 전체 선언을 구분한다. 한 import문이 여러 대상을 가리킬 수 있으므로 관계 수를 구문 수로 표현하지 않는다. 평가하지 않은 항목의 통과·안전을 주장하지 않는다. 관계가 없거나 잘린 경우 영향 없음·미사용·테스트 없음으로 바꾸지 않는다.

## Implementation constraints
- Framework/styling system: 기존 정적 HTML·ES modules·CSS·Pyodide AST.
- Design-token constraints: 별도 UI 프레임워크·디자인 시스템 추가 없음.
- Performance constraints: 기존 파일·바이트 제한 유지. 로컬은 목록100000개·Python100개·파일당64KiB·읽기 동시6개를 한도로 하며 .git·가상환경·의존성·캐시를 제외하고 생략을 표시한다. File 읽기 중에도 취소·90초 제한을 적용한다. PR은 최대300개 변경 목록에서 사용자가 지정한 현재 경로를 먼저 적용한 뒤 Python 원본100개를 읽는다. 원본 캐시는 PR·정규화 경로 범위별로 구분하고 중단·읽기 실패는 재사용하지 않는다. 저장소는 파일80개·관계400개·미확인100개·파일당선언20개, 선택 도표는 이웃12개와 정확한 생략 수 표시. tree의 미수집 파일 경로도 충돌 확인에 사용한다.
- Compatibility constraints: 대상 소스 실행·import 없음. OpenAI API·키·추가 서버 없음. 사용 목적·개선 후보 전환은 이미 읽은 그래프와 선언만 사용하며 추가 GitHub 조회·재분석을 하지 않는다. 개선 후보는 코드 변경을 적용하지 않은 검토 가정이다. 전제·변경 관계·적용 행동·단점·확인 조건을 함께 표시하고, 실제 테스트·운영 개선·최적 설계가 검증됐다고 표현하지 않는다. import 순환의 한 관계를 조정하는 시나리오는 다른 순환까지 해결한다고 주장하지 않는다.
- Proposal comparison bounds: 선택 파일별 규칙 최대2개, 후보별 소스 근거6곳·정확한 생략 수. 순환 도표는 가장 짧은 확인 경로의 파일 최대6개이며 더 긴 순환을 잘라 그리지 않는다. 역할 분리는 기존 import를 어느 역할로 배분할지 추정하지 않고 선택 파일의 직접 선언 공존만 비교한다.
- Test/screenshot expectations: 그래프 정확성·누락·이전행·비실행 테스트, 실제 공개 PR 브라우저·390px·SVG 확인.

## Open questions
- [ ] 실제 라우터 등록·재수출·함수 호출을 확장하려면 실행 여부와 설정 경계를 별도로 설계한다.
