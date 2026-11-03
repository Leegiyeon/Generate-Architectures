"""사용자가 제공한 부하 테스트의 집계 증거를 보수적으로 평가하는 읽기 전용 엔진.

개별 호출·URL·IP·실제 AWS 계정·키/원본 로그를 수집하지 않습니다.
실측값은 서명/진위·테스트 환경을 검증한 것이 아니라 사용자 제공 수치입니다.
실측 처리량을 운영용 최소/최대 용량이나 가격표로 직접 변환하지 않습니다.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
from pathlib import Path
import re

ID = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
REGION = re.compile(r"[a-z]{2}(?:-gov)?-[a-z]+-\d\Z")
CANDIDATES = ("fargate", "ec2", "lambda")
MAX_BYTES = 32768
REFERENCES = {
    "aws_load_testing": "https://docs.aws.amazon.com/wellarchitected/latest/framework/perf_process_culture_load_test.html",
    "ecs_scaling": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html",
    "lambda_concurrency": "https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html",
}


def _number(value, title, lower=0, upper=1000000000000, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(title + "에는 유한한 숫자가 필요합니다.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(title + "에는 유한한 숫자가 필요합니다.") from None
    if not number.is_finite() or not Decimal(lower) <= number <= Decimal(upper):
        raise ValueError(title + "은 지정된 범위 내여야 합니다.")
    if positive and number == 0:
        raise ValueError(title + "은 0보다 커야 합니다.")
    return number


def read_capacity_evidence(root, path):
    """옵트인 사용자 입력 파일만 읽음. 테스트를 직접 실행하거나 AWS에 접근하지 않음."""
    if not path:
        return None
    base = Path(root).resolve()
    candidate = base / path
    if candidate.is_symlink():
        raise ValueError("부하 테스트 증거 입력은 심볼릭 링크일 수 없습니다.")
    file = candidate.resolve()
    if not file.is_relative_to(base) or not file.is_file() or file.stat().st_size > MAX_BYTES:
        raise ValueError("증거 JSON은 저장소 내부의 32KB 이하 파일이어야 합니다.")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("부하 테스트 증거 JSON을 읽을 수 없습니다.") from exc
    return validate_capacity_evidence(data)


def validate_capacity_evidence(data):
    """자유 메모/엔드포인트·RawLog 금지: 집계 지표와 구분 ID만 허용."""
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "benchmark_id", "tested_on", "environment",
        "region", "workload_id", "targets", "allow_linear_extrapolation", "results"
    } or data["schema_version"] != "1.0":
        raise ValueError("성능 증거 입력 형식(schema_version 1.0)이 유효하지 않습니다.")
    for name in ("benchmark_id", "workload_id"):
        if not isinstance(data[name], str) or not ID.fullmatch(data[name]):
            raise ValueError(name + "은 64자 이하의 영문/숫자 식별자여야 합니다.")
    try:
        if not isinstance(data["tested_on"], str) or date.fromisoformat(data["tested_on"]).isoformat() != data["tested_on"]:
            raise ValueError
    except ValueError:
        raise ValueError("tested_on은 YYYY-MM-DD 실제 날짜여야 합니다.") from None
    if data["environment"] not in ("staging", "isolated_test", "production_like"):
        raise ValueError("실행 환경은 staging/isolated_test/production_like 중 하나여야 합니다.")
    if not isinstance(data["region"], str) or not REGION.fullmatch(data["region"]):
        raise ValueError("증거 리전은 AWS 리전 코드여야 합니다.")
    if not isinstance(data["allow_linear_extrapolation"], bool):
        raise ValueError("선형 확장 가정 여부는 true/false로 명시해야 합니다.")
    targets = data["targets"]
    if not isinstance(targets, dict) or set(targets) != {
        "peak_rps", "p95_latency_ms", "max_error_rate_percent", "min_test_duration_seconds"
    }:
        raise ValueError("요구 목표의 피크 RPS/p95/오류율/최소 시험 시간 모두 필요합니다.")
    _number(targets["peak_rps"], "peak_rps", 0, 10000000, positive=True)
    _number(targets["p95_latency_ms"], "p95_latency_ms", 0, 600000, positive=True)
    _number(targets["max_error_rate_percent"], "max_error_rate_percent", 0, 100)
    _number(targets["min_test_duration_seconds"], "min_test_duration_seconds", 0, 86400, positive=True)
    results = data["results"]
    if not isinstance(results, list) or not 1 <= len(results) <= 3:
        raise ValueError("후보별 테스트 요약은 1~3개여야 합니다.")
    seen = set()
    for row in results:
        if not isinstance(row, dict) or set(row) != {
            "candidate", "sustained_rps", "p95_latency_ms", "error_rate_percent",
            "duration_seconds", "observed_capacity_units", "avg_duration_ms",
            "scale_out_observed"
        }:
            raise ValueError("테스트 요약은 집계 지표만 허용합니다(엔드포인트/시크릿/로그 제외).")
        key = row["candidate"]
        if not isinstance(key, str) or key not in CANDIDATES or key in seen:
            raise ValueError("중복되거나 지원하지 않는 테스트 후보입니다.")
        seen.add(key)
        _number(row["sustained_rps"], "sustained_rps", 0, 10000000)
        _number(row["p95_latency_ms"], "p95_latency_ms", 0, 600000)
        _number(row["error_rate_percent"], "error_rate_percent", 0, 100)
        _number(row["duration_seconds"], "duration_seconds", 0, 86400, positive=True)
        count = _number(row["observed_capacity_units"], "observed_capacity_units",
                        1, 1000000, positive=True)
        if count != count.to_integral_value():
            raise ValueError("관측 용량 단위 수는 정수여야 합니다.")
        if not isinstance(row["scale_out_observed"], bool):
            raise ValueError("scale_out_observed는 명시적 true/false여야 합니다.")
        if key == "lambda":
            _number(row["avg_duration_ms"], "Lambda 평균 실행시간(ms)", 0, 900000,
                    positive=True)
        elif row["avg_duration_ms"] is not None:
            raise ValueError("Fargate/EC2에서 Lambda 평균 실행시간을 대입할 수 없습니다.")
    return data


def analyze_capacity_evidence(data, requirements, alternative_data=None):
    """입력된 단 한 번의 부하 실험 결과를 목표와 대조. AWS/SLO 검증이 아님."""
    if data is None:
        return {
            "schema_version": "1.0", "status": "needs_input", "benchmark_id": None,
            "results": [], "all_observed_targets_met": False,
            "requirements_matched": None, "evidence_authenticity_verified": False,
            "autoscaling_verified": False, "production_ready": False,
            "note": "집계형 부하 시험 증거가 입력되지 않아 처리량·임계값을 검토하지 않았습니다.",
        }
    validate_capacity_evidence(data)
    checks = {}
    for key, value in (
        ("peak_rps", data["targets"]["peak_rps"]),
        ("latency_target_ms", data["targets"]["p95_latency_ms"]),
        ("region", data["region"]),
    ):
        if key in requirements:
            checks[key] = (data["region"] == requirements["region"] if key == "region"
                           else Decimal(str(requirements[key])) == Decimal(str(value)))
    if alternative_data is not None:
        checks["alternative_workload_id"] = (
            alternative_data["workload"]["id"] == data["workload_id"])
        checks["alternative_peak_rps"] = (
            Decimal(str(alternative_data["workload"]["peak_rps"])) ==
            Decimal(str(data["targets"]["peak_rps"])))
        checks["alternative_region"] = alternative_data["region"] == data["region"]
        expected = {x["id"] for x in alternative_data["candidates"]}
    else:
        expected = {x["candidate"] for x in data["results"]}
    found = {x["candidate"] for x in data["results"]}
    requirements_matched = all(checks.values())
    results = []
    any_failed = False
    all_met = bool(expected) and expected == found
    for entry in sorted(data["results"], key=lambda x:CANDIDATES.index(x["candidate"])):
        target = data["targets"]
        meets = {
            "sustained_rps": Decimal(str(entry["sustained_rps"])) >= Decimal(str(target["peak_rps"])),
            "p95_latency_ms": Decimal(str(entry["p95_latency_ms"])) <= Decimal(str(target["p95_latency_ms"])),
            "error_rate_percent": Decimal(str(entry["error_rate_percent"])) <= Decimal(str(target["max_error_rate_percent"])),
            "duration_seconds": Decimal(str(entry["duration_seconds"])) >= Decimal(str(target["min_test_duration_seconds"])),
        }
        status = ("observed_targets_met_limited" if all(meets.values()) else
                  "observed_targets_not_met")
        if not all(meets.values()):
            any_failed = True
        all_met = all_met and all(meets.values())
        # 단지 제공된 하나의 실행에서 관찰한 처리량/용량 단위 평균일 뿐
        # 실제 개별 Task/인스턴스의 처리량 또는 선형 확장의 증거가 아닙니다.
        theoretical = None
        if entry["candidate"] in ("fargate", "ec2"):
            if data["allow_linear_extrapolation"] and Decimal(str(entry["sustained_rps"])) > 0:
                theoretical = {
                    "unit": "ecs_tasks" if entry["candidate"] == "fargate" else "ec2_instances",
                    "suggested_count": int((
                        Decimal(str(target["peak_rps"])) * Decimal(str(entry["observed_capacity_units"])) /
                        Decimal(str(entry["sustained_rps"]))
                    ).to_integral_value(rounding=ROUND_CEILING)),
                    "status": "unverified_linear_extrapolation_not_capacity_recommendation",
                    "formula": "ceil(target_peak_rps * observed_units / observed_sustained_rps)",
                    "assumption": "선형 처리량 증가 가정은 사용자 동의가 있더라도 실증되지 않았습니다.",
                }
        elif entry["candidate"] == "lambda":
            theoretical = {
                "unit": "approximate_mean_concurrent_executions",
                "suggested_count": int((
                    Decimal(str(target["peak_rps"])) * Decimal(str(entry["avg_duration_ms"])) / 1000
                ).to_integral_value(rounding=ROUND_CEILING)),
                "status": "theoretical_steady_state_not_quota_verified",
                "formula": "ceil(target_rps * observed_mean_duration_ms / 1000)",
                "assumption": "평균 실행시간 기반 이론값이며 순간 버스트·쿼터·예약/프로비저닝 동시성 반영 전입니다.",
            }
        results.append({
            "candidate": entry["candidate"], "status": status,
            "meets_user_supplied_test_thresholds": meets,
            "observed": {
                "sustained_rps": entry["sustained_rps"],
                "p95_latency_ms": entry["p95_latency_ms"],
                "error_rate_percent": entry["error_rate_percent"],
                "duration_seconds": entry["duration_seconds"],
                "observed_capacity_units": entry["observed_capacity_units"],
                "unit_semantics": ("max_concurrent_executions" if entry["candidate"] == "lambda"
                                   else "tasks" if entry["candidate"] == "fargate" else "instances"),
                "scale_out_observed": entry["scale_out_observed"],
                "avg_duration_ms": entry["avg_duration_ms"],
            },
            "planning_only": theoretical, "quota_checked": False,
            "production_like_environment_verified": False,
            "autoscaling_policy_verified": False,
        })
    status = ("requirements_mismatch" if not requirements_matched else
              "benchmark_candidates_incomplete" if expected != found else
              "observed_targets_not_met" if any_failed else
              "observed_targets_met_limited")
    return {
        "schema_version": "1.0", "status": status,
        "benchmark_id": data["benchmark_id"], "tested_on": data["tested_on"],
        "environment_claimed": data["environment"], "workload_id": data["workload_id"],
        "region": data["region"],
        "targets": dict(data["targets"]), "requirements_checks": checks,
        "requirements_matched": requirements_matched,
        "expected_candidates": sorted(expected), "observed_candidates": sorted(found),
        "results": results,
        "all_observed_targets_met": status == "observed_targets_met_limited" and all_met,
        "evidence_authenticity_verified": False,
        "autoscaling_verified": False, "production_ready": False,
        "cost_adjustment_automated": False, "aws_quotas_verified": False,
        "note": ("입력은 사용자가 제출한 집계 부하 테스트 수치로 진위 검증·운영 환경 동일성·"
                 "Scale-out/Failover·Service Quotas·SLO 충족을 보장하지 않습니다. "
                 "기록된 선형 용량 수는 동의된 산술 시뮬레이션이며 Task/EC2 수로 자동 적용하지 않습니다."),
        "references": REFERENCES,
    }


def markdown_capacity(report):
    rows=["# 사용자 제공 부하 테스트 용량·성능 근거 검토", "",
          "> AWS 계정/실측 로그 직접 검증 없음. 사용자가 제출한 집계 수치만 평가.",
          "", "- 상태: " + report["status"], "- 운영 적합성 인증: 미실시",
          "- AWS Service Quotas 확인: 미실시", "- 자동 인프라 조정: 없음", ""]
    if report["status"] == "needs_input":
        rows+=["## 입력 대기", "", "예시와 조건은 docs/CAPACITY_EVIDENCE.md 참조.", ""]
        return "\n".join(rows)
    rows+=["- 기준 테스트: " + report["benchmark_id"],
           "- 테스트 날짜: " + report["tested_on"],
           "- 실행 환경(제출자 주장): " + report["environment_claimed"],
           "- 요구사항 일치: " + str(report["requirements_matched"]), "",
           "## 입력 성능 목표와 관측치", "",
           "| 패턴 | 관측 RPS | 관측 p95 ms | 관측 오류 % | 테스트 시간 s | 임계값 충족(제출값 한정) |",
           "| --- | ---: | ---: | ---: | ---: | --- |"]
    for r in report["results"]:
        o=r["observed"]
        rows.append("| " + r["candidate"] + " | " +
                    str(o["sustained_rps"]) + " | " + str(o["p95_latency_ms"]) +
                    " | " + str(o["error_rate_percent"]) + " | " +
                    str(o["duration_seconds"]) + " | " + r["status"] + " |")
        if r["planning_only"]:
            p=r["planning_only"]
            rows+=["- " + r["candidate"] + " 이론 산출: " + str(p["suggested_count"]) +
                   " " + p["unit"] + " — " + p["status"] + " / " + p["formula"],
                   "  - " + p["assumption"]]
    rows+=["", "## 추가 확인이 필요한 항목", "",
           "- 부하 도구·테스트 환경/데이터·대상 DB, 테스트 기간/동일 워크로드 재현성과 실제 SLA 검증",
           "- AWS 리전별 Service Quotas·Lambda 동시성 및 스로틀링/콜드스타트",
           "- ECS/EC2 Auto Scaling 확장 지연·단위별 부하 분산·장애 전환·다중 AZ",
           "- 사용자 제공 측정값의 진위 및 원본 로그 확인(이 도구는 원본을 수집하지 않음)",
           "- 운영 비용 환산은 인스턴스/Task 크기·가동 시간·통신/백업 등 추가 근거 필요",
           "",report["note"],""]
    return "\n".join(rows)
