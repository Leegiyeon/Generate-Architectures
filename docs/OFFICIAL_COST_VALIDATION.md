# 공식 AWS 비용 계산 예시 회귀 검증

Issue #15의 일부로, **2026-11-03에 확인한 공식 페이지의 예시 숫자**를 고정해 기존 계산을 대조한다. 가격 적용 시작일은 페이지에서 확인되지 않았다. 확인일은 가격 유효 시작일이 아니며, 이 문서는 현재 가격표나 사용자 계정 견적이 아니다. 테스트는 네트워크·AWS 자격증명·유료 API를 사용하지 않는다.

## Fargate: 두 가지 단일 단가 사례

근거: [AWS Fargate Pricing — Pricing Examples 1·2](https://aws.amazon.com/fargate/pricing/). 예시 리전은 **US East (N. Virginia), `us-east-1`**.

두 사례 모두 5개 태스크, 일 600초, 30일, 태스크당 1 vCPU·메모리 2 GB·임시 저장소 30 GB다. 공식 예시에서 추가 과금 저장소는 10 GB다. 이미 확정된 예시 수량을 시간 단위로 바꾸면 CPU 25 vCPU-Hours, 메모리 50 GB-Hours, 저장소 250 GB-Hours다.

| 항목 | Linux/x86 초당 USD | Linux/ARM 초당 USD | 단위 |
| --- | ---: | ---: | --- |
| CPU | 0.000011244 | 0.0000089944 | vCPU-second |
| 메모리 | 0.000001235 | 0.0000009889 | GB-second |
| 추가 저장소 | 0.0000000308 | 0.0000000308 | GB-second |

기존 `manual_quote` 입력으로 `초당 단가 × 3600 × 시간 단위 수량`을 계산한다. 내부 Decimal 계산은 반올림하지 않고, 공식 페이지의 센트 표시에만 맞춰 대조한다.

| 공식 사례 | CPU USD | 메모리 USD | 저장소 USD | 표시 합계 USD |
| --- | ---: | ---: | ---: | ---: |
| Example 1, Linux/x86 | 1.01 | 0.22 | 0.03 | 1.26 |
| Example 2, Linux/ARM | 0.81 | 0.18 | 0.03 | 1.02 |

저장소 포함량은 **예시에서 이미 차감한 수량**을 사용한다. 제품이 무료량이나 태스크 최소 과금 시간을 자동 적용하는지 검증하는 테스트가 아니다. 세 시나리오에는 같은 예시 수량을 반복하며 부하 예측으로 해석하지 않는다. 세금·할인·네트워크·로그·IPv4·다른 서비스 비용은 검증 범위 밖이다.

## API Gateway: 구간별 누적 과금 사례

근거: [Amazon API Gateway Pricing — REST APIs, Edge Optimized and Regional APIs, 15 billion calls example](https://aws.amazon.com/api-gateway/pricing/). 예시가 명시한 지역은 US East (N. Virginia, Ohio), US West (Oregon), Asia Pacific (Mumbai)다. 캐시 없는 REST API의 **요청 비용 부분만** 대조한다.

| 요청 구간 | 단가 USD/백만 요청 | 예시 요청 비용 USD |
| --- | ---: | ---: |
| 처음 333백만 | 3.50 | 1,165.50 |
| 다음 667백만 | 2.80 | 1,867.60 |
| 다음 14,000백만 | 2.38 | 33,320.00 |
| 합계 15,000백만 | 구간별 누적 | 36,353.10 |

`amount_for_tiers`에 요청당 단가로 정확히 변환하여 입력하고, 구간 경계 및 최종 합계를 확인한다. 150억 요청을 넘는 가격 구간은 이 예시만으로 확정하지 않는다. 따라서 테스트의 마지막 끝값은 `Inf`가 아니라 150억이며, 실제 GetProducts 응답이나 SKU를 가장하지 않는다. 이 유한 예시 표는 0부터 무한대까지 완전한 가격표를 요구하는 `interpret_price_dimensions` 검증을 통과했다고 주장하지 않는다.

데이터 전송·응답 크기의 청구량 변환·무료량·계정 합산·할인·다른 서비스 비용은 테스트하지 않는다. API Gateway의 모든 요금 모델을 지원한다는 의미도 아니다.

## 실행 및 남은 검증

```sh
python -m unittest tests.test_official_cost_examples -v
```

이 검증은 공개 예시 세 개의 산술 회귀만 고정한다. 실제 리전별 SKU 선택, AWS Price List 응답과의 대조, 계정별 결합 계층/크레딧, 전체 아키텍처의 누락 비용, 실제 부하와 용량의 연결은 별도 검증이 필요하므로 Issue #15를 완료 처리하지 않는다. 공식 페이지 변경 시 확인일·입력값·기대값을 함께 검토한다.
