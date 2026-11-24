# FastAPI PR Review — 사용 초대 문구

아래 문구는 사용자가 직접 공유할 준비 자료입니다. 외부 게시·DM·댓글을 발송한 기록은 아닙니다. 피드백 응답을 사용 조건으로 요구하지 않습니다.

## 짧은 소개

```text
FastAPI PR에서 API·DB 변경을 검토하시나요?
공개 GitHub PR 링크를 넣으면 라우트·응답 모델·DB 필드·마이그레이션의 변경 근거와 코드 구조도를 볼 수 있는 무료 웹 도구를 만들었습니다.

로그인·설치·OpenAI API 키 없이 사용할 수 있습니다. 첫 화면의 ‘저장된 결과 먼저 보기’로 실제 예제를 바로 확인하거나, 지금 검토 중인 공개 FastAPI PR을 넣어 보세요.
https://leegiyeon.github.io/Generate-Architectures/

Python 코드의 정적 선언을 비교하며, 실제 실행 경로나 DB 상태는 별도로 확인해야 합니다.
```

## 개발 커뮤니티용 소개

```text
[무료 도구] 공개 FastAPI PR의 API·DB 변경을 코드 근거와 함께 확인하기

FastAPI 프로젝트를 개발·리뷰하는 분을 위한 FastAPI PR Review를 만들었습니다.
공개 GitHub PR 링크를 넣고 API 사용 / DB 변경 / 전체 관점을 선택하면 다음을 확인할 수 있습니다.

• 라우트·핸들러·직접 선언한 모델 필드·마이그레이션 변경
• 변경 전후의 파일·라우트·모델 구조도와 원본 파일·행 링크
• 경로·모델별 범위 선택, 요약 복사와 분석 설정 링크 공유

저장소의 현재 구조가 궁금하면 공개 저장소 URL과 Python 소스 루트로 직접 import 관계도 탐색할 수 있습니다.

체험: https://leegiyeon.github.io/Generate-Architectures/
로그인·설치·OpenAI API 키 없이 무료로 사용할 수 있습니다. ‘저장된 결과 먼저 보기’에서 실제 출력과 코드 근거를 확인한 뒤 최근 검토 중인 공개 FastAPI PR에 적용해 보세요.

분석은 브라우저에서 수행하고 대상 코드를 실행하지 않습니다. Python 소스 최대 100개·파일당 64 KiB와 GitHub 비인증 조회 한도가 적용됩니다. 직접 선언과 정적 관계를 다루므로 실제 호출·최종 라우터 등록·DB 실행 상태·운영 인프라는 확인하지 못합니다.
```

## Short English invitation

```text
Reviewing API or database changes in a public FastAPI PR?

FastAPI PR Review compares route handlers, directly declared model fields and migrations, with source links and before/after code diagrams.

Try an example or paste your public GitHub PR:
https://leegiyeon.github.io/Generate-Architectures/

Free, with no sign-in, installation or OpenAI API key required. The interface and reports are currently in Korean. It analyzes static Python declarations in your browser, not runtime behavior or the live database. Limits: 100 Python files, 64 KiB per file, and GitHub's unauthenticated request limits.
```

## 공유 이미지

[대표 이미지 (1200×630 JPEG)](https://leegiyeon.github.io/Generate-Architectures/social-preview.jpg)를 소개 글에 첨부할 수 있습니다. [원본 SVG](assets/fastapi-pr-social-card.svg)는 기존 색상과 #2144의 저장 근거로 구성했습니다. 사이트의 OG/Twitter 메타데이터도 같은 이미지를 가리킵니다. 각 플랫폼의 미리보기 반영·캐시는 별도이며 노출을 보장하지 않습니다.

## 설명과 함께 보낼 예제 링크

- [DB 변경 예제 — created_at 필드·마이그레이션](https://leegiyeon.github.io/Generate-Architectures/#pr=https%3A%2F%2Fgithub.com%2Ffastapi%2Ffull-stack-fastapi-template%2Fpull%2F2144&focus=db&path=backend%2Fapp)
- [API 변경 예제 — 사용자 삭제 핸들러](https://leegiyeon.github.io/Generate-Architectures/#pr=https%3A%2F%2Fgithub.com%2Ffastapi-users%2Ffastapi-users%2Fpull%2F1258&focus=api&path=fastapi_users%2Frouter%2Fusers.py)

두 링크는 PR·관점·경로를 입력해 줍니다. 받은 사람이 **‘변경 확인’을 눌러야 분석**하며, 실행 시점의 최신 PR을 읽습니다. 저장된 결과나 특정 PR 커밋을 전달하는 링크가 아니므로 결과 수치를 고정해 홍보하지 않습니다. 분석 후 본인 PR과 범위도 ‘분석 설정 링크 복사’로 공유할 수 있습니다.

## 직접 공유할 때의 순서

1. **본인의 개발 채널**: 개인 블로그·SNS·포트폴리오에 짧은 소개와 실제 결과 화면을 올립니다. 이미지에 보이는 PR과 정적 분석 범위를 함께 적습니다.
2. **FastAPI·Python 커뮤니티**: 프로젝트 소개가 허용된 게시판의 최신 규칙을 확인한 뒤 관련 있는 곳 한 곳에 소개합니다. 같은 글을 반복 게시하거나 무관한 PR에 홍보 댓글을 달지 않습니다.
3. **기존 개발자 지인 채널**: 도구 소개를 받는 데 동의한 대화에서 지금 검토 중인 공개 PR에 써 보도록 안내합니다. 답변·설문을 체험의 조건으로 붙이지 않습니다.

게시 여부와 확인된 실사용·재사용 성과는 [기존 진행 기록](FASTAPI_PR_TEST.md#현재-목표와-진행률)에서만 관리합니다. 예제 실행·조회 수·재사용 의향은 본인 PR 실사용이나 다른 PR에서의 실제 재사용으로 계산하지 않습니다. 이름·이메일·비공개 PR 정보 없이 확인 가능한 범위만 기록합니다. 이 자료 준비나 에이전트 검증은 실제 사용자 확보의 증거가 아닙니다.
