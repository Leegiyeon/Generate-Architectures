# 집계 부하 테스트 기반 AWS 용량·성능 검토 (Issue #15 4차)

> **이 기능은 부하 테스트를 직접 실행하지 않습니다.** 사용자가 수행한 시험의 집계 숫자만 가져와 피크 RPS, p95 응답시간, 오류율, 테스트 지속시간의 임계값과 비교합니다. 원본 로그, 실제 API URL, 계정/키/비밀정보를 수집하거나 AWS 계정을 조회하지 않습니다.

## 시작하기

[비기밀 합성 데이터 예시](../examples/capacity-evidence.example.json)는 실제 서비스에서 측정한 데이터가 아닙니다. 운영 시험 집계값을 입력한 뒤 GitHub Actions → AWS 아키텍처 검토 자동화 → Run workflow → capacity_evidence에서 해당 JSON의 저장소 내부 경로를 지정하세요.

CLI: python3 scripts/recommend_architecture.py --repo . --output architecture-output --requirements .architecture/requirements.json --alternative-cost-input examples/alternative-cost-comparison.example.json --capacity-evidence examples/capacity-evidence.example.json

기존 대안 비용 파일 입력은 선택적입니다. 함께 지정하면 동일 workload ID, AWS 리전, 피크 RPS 및 비용 후보들이 일치하는지 확인합니다. 다만 부하 테스트의 합격이 서비스 비용 입력값의 진위를 검증하지는 않습니다.

## 입력 계약

schema_version 1.0에 다음 항목만 포함할 수 있습니다.

- benchmark_id / workload_id: 영문·숫자·점·밑줄·대시만 포함하는 64자 이하 식별자.
- tested_on: YYYY-MM-DD 시험 날짜. 기록의 실제 진위는 확인하지 않습니다.
- environment: staging / isolated_test / production_like 중 하나. 사용자 선언값입니다.
- region: AWS 리전.
- targets: peak_rps, p95_latency_ms, max_error_rate_percent, min_test_duration_seconds. 모두 사용자가 명시한 평가 기준입니다.
- allow_linear_extrapolation: true로 명시한 경우에만 ECS/EC2 선형 확장 가정으로 산술적 예상 개수를 표시합니다.
- results: 후보별 candidate, sustained_rps, p95_latency_ms, error_rate_percent, duration_seconds, observed_capacity_units, avg_duration_ms, scale_out_observed.

observed_capacity_units는 ECS/EC2에서 각각 테스트 중 동작한 Task/인스턴스 수입니다. Lambda에서는 최대 관측 동시 실행 수이며, 이 수를 ECS/EC2 컴퓨팅 수량과 직접 비교할 수 없습니다. avg_duration_ms는 Lambda에서만 사용하고 ECS/EC2는 null입니다.

입력 스키마는 자유 형식 텍스트, 로그, IP 주소 및 URL을 허용하지 않습니다. 파일을 저장소에 올릴 때에는 테스트 대상의 보안 등급과 GitHub Artifact 접근 권한을 확인하세요.

## 결과 판정

개별 후보는 측정 지속 RPS ≥ 목표 피크 RPS, p95 응답시간 ≤ 목표 p95, 오류율 ≤ 허용 오류율, 테스트 시간 ≥ 최소 테스트 시간 조건을 모두 충족해야 observed_targets_met_limited 상태가 됩니다.

이 상태는 제출된 집계 수치가 입력 임계값을 충족한다는 뜻일 뿐, 실제 운영환경의 성능·서비스 가용성·보안 또는 제출된 데이터의 진위를 입증하지 않습니다. 전체 결과는 production_ready=false, evidence_authenticity_verified=false, autoscaling_verified=false, aws_quotas_verified=false로 유지됩니다.

### ECS/EC2 계산 — 사용자 선형 가정 동의가 있을 때만

계획용 개수 = ceil(목표 피크 RPS × 관측 Task 또는 EC2 인스턴스 수 ÷ 관측 RPS).

이 계산은 단순 산술 시뮬레이션으로, 실제 최소 필요 수량이나 Auto Scaling 배포값이 아닙니다. DB/네트워크 병목, 지연, AZ 장애, 쿼터, 캐시와 분산 불균형은 반영되지 않습니다. allow_linear_extrapolation=false면 계산하지 않습니다.

### Lambda — 평균 실행시간 기반 정상상태 동시성

계획용 근사값 = ceil(목표 RPS × 관측 평균 함수 실행시간(ms) ÷ 1000).

AWS의 동시성 기본 공식에 기반하지만 순간 버스트·계정 제한·프로비저닝/예약 동시성, 스로틀링 또는 실제 서비스의 응답성은 검증하지 않습니다.

참고 문서:
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html
- https://docs.aws.amazon.com/wellarchitected/latest/framework/perf_process_culture_load_test.html

## 기존 비용 대안 비교 연결

alternative_cost_input과 capacity_evidence를 함께 지정한 경우, 제출된 부하 데이터에 후보 누락·요구사항 불일치·측정값 미달이 있으면 기존 비용 비교의 산술 차액을 표시하지 않고 capacity_evidence_review_required 상태로 기록합니다.

모든 후보가 사용자 시험 기준을 충족하더라도 실제 워크로드·운영 환경 동등성이 검증된 것은 아니므로 기존 비용 비교의 modeled_items_comparable_unverified는 **입력된 비용 항목에 한정**합니다. Task/EC2/Lambda 수량이나 가격은 자동 재계산하지 않으며 ADR 또는 선택된 AWS 설계도를 변경하지 않습니다.

## 출력 및 유지보수

capacity-evidence.json/md, START-HERE.html/md의 측정 요약, deliverables/04-cost-capacity.md의 시험 근거, alternative-cost-comparison.json의 차단 상태가 생성됩니다.

서비스 팀은 테스트 수행자·테스트 코드 버전/성능 프로파일과 실제 AWS Service Quotas, 보안/네트워크 정책, DB·외부 API 병목, 확장 지연 및 장애 복구 시험 등을 별도로 기록/승인해야 합니다. 부하 테스트 전 대상 시스템 소유자의 승인을 받고 AWS의 관련 서비스 사용 정책을 따라야 합니다.
