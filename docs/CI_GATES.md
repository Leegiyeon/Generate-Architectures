# main 병합 전 필수 CI 설정

2026-11-04 확인: `main`의 `protected=false`, repository rulesets는 빈 배열이었다. branch protection 상세 API는 연결된 GitHub App의 관리 권한 제한으로 403을 반환했다. 현재 자동 테스트가 존재해도 실패한 PR의 병합을 저장소 정책으로 차단하지는 않는다.

## 적용할 최소 정책

저장소 관리자가 `main` 대상 branch protection 또는 ruleset에서 **필수 상태 검사 `recommend` (GitHub Actions)**를 지정한다. 실제 main 커밋 `46e9c934`의 check-runs에서 `recommend`와 `cleanup`을 확인했다. `recommend`는 Python 회귀 검사와 보고서 브라우저 검사 job이며, `cleanup`은 병합 브랜치 정리 job이므로 품질 게이트를 대신하지 않는다.

이 문서는 정책을 적용하지 않는다. 관리자는 정책 적용 후 테스트가 실패한 PR의 병합이 차단되고, 최신 커밋의 `recommend`가 성공한 PR이 병합 가능해지는지 확인해야 한다. 관리자 우회·예외 허용 범위도 함께 확인한다. API 토큰이나 관리 자격증명을 코드/채팅에 넣을 필요는 없다.

분석 보고서의 사람 승인, 실제 AWS 성능·보안·비용 검증은 CI 통과와 별개다.
