"""공식 AWS 예시를 고정한 오프라인 산술 회귀; 현재 가격/SKU 검증은 아님.

출처·확인일·리전·제외 범위: docs/OFFICIAL_COST_VALIDATION.md
테스트에서는 AWS API/자격증명/네트워크를 사용하지 않습니다.
"""
from decimal import Decimal, ROUND_HALF_UP
import unittest

from scripts.aws_price_dimensions import amount_for_tiers
from scripts.cost_estimator import estimate_costs
from scripts.cost_scenarios import validate_scenario_config


FARGATE_SOURCE = "https://aws.amazon.com/fargate/pricing/"
OBSERVED_ON = "2026-11-03"


def cents(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fargate_example(cpu_per_second, memory_per_second):
    """공식 5 tasks × 600 seconds × 30 days를 지원되는 시간 단위로 변환.

    Storage 수량은 공식 예시에 명시된 30 GB 중 추가 과금 10 GB만 사용.
    최소 과금 시간/무료 저장량을 제품이 자동 추론한다는 의미는 아닙니다.
    """
    items = []
    for name, unit, quantity, per_second in (
        ("cpu", "vCPU-Hours", 25, cpu_per_second),
        ("memory", "GB-Hours", 50, memory_per_second),
        ("extra_storage", "GB-Hours", 250, "0.0000000308"),
    ):
        items.append({
            "id": name, "service": "ecs_fargate", "unit": unit,
            "quantities": {key: quantity for key in ("minimum", "baseline", "peak")},
            "rate": {
                "kind": "manual_quote",
                "unit_price_usd": str(Decimal(per_second) * 3600),
                "source": FARGATE_SOURCE, "as_of": OBSERVED_ON,
            },
        })
    return validate_scenario_config({
        "schema_version": "2.0", "region": "us-east-1", "items": items,
    })


class OfficialCostExampleTests(unittest.TestCase):
    def assert_fargate_example(self, config, exact_lines, displayed_lines, displayed_total):
        report = estimate_costs(config, live=False)
        # Equal quantities deliberately repeat the same official example in each slot.
        for scenario in report["scenarios"].values():
            self.assertTrue(scenario["complete_for_provided_items"])
            amounts = {line["id"]: Decimal(line["monthly_amount_usd"])
                       for line in scenario["lines"]}
            self.assertEqual(amounts, {key: Decimal(value)
                                      for key, value in exact_lines.items()})
            self.assertEqual({key: cents(value) for key, value in amounts.items()},
                             {key: Decimal(value) for key, value in displayed_lines.items()})
            self.assertEqual(cents(scenario["monthly_total_usd"]), Decimal(displayed_total))
            for line in scenario["lines"]:
                self.assertEqual(line["source_reference"], FARGATE_SOURCE)
                self.assertEqual(line["price_as_of"], OBSERVED_ON)
                self.assertIsNone(line["sku"])
        # A complete example covers the supplied items, not the entire AWS bill.
        self.assertIn("전체 AWS 청구액이 아닙니다", report["note"])

    def test_fargate_linux_x86_example_1(self):
        self.assert_fargate_example(
            fargate_example("0.000011244", "0.000001235"),
            {"cpu": "1.0119600", "memory": "0.2223000", "extra_storage": "0.02772000"},
            {"cpu": "1.01", "memory": "0.22", "extra_storage": "0.03"},
            "1.26",
        )

    def test_fargate_linux_arm_example_2(self):
        self.assert_fargate_example(
            fargate_example("0.0000089944", "0.0000009889"),
            {"cpu": "0.80949600", "memory": "0.17800200", "extra_storage": "0.02772000"},
            {"cpu": "0.81", "memory": "0.18", "extra_storage": "0.03"},
            "1.02",
        )

    def test_api_gateway_rest_15_billion_example_graduated_requests(self):
        # Official example: edge-optimized/regional REST API, no caching.
        # Rates converted from USD/million to USD/request without rounding.
        # Its three priced slices stop at 15 billion: no inferred Inf/SKU/API response.
        tiers = [
            {"begin": "0", "end": "333000000", "usd_per_unit": "0.00000350"},
            {"begin": "333000000", "end": "1000000000", "usd_per_unit": "0.00000280"},
            {"begin": "1000000000", "end": "15000000000", "usd_per_unit": "0.00000238"},
        ]
        self.assertEqual(amount_for_tiers(tiers, 333000000), Decimal("1165.50"))
        self.assertEqual(amount_for_tiers(tiers, 1000000000), Decimal("3033.10"))
        self.assertEqual(amount_for_tiers(tiers, 15000000000), Decimal("36353.10"))
        # A flat application of the last rate would incorrectly yield 35,700 USD.
        self.assertNotEqual(amount_for_tiers(tiers, 15000000000), Decimal("35700"))


if __name__ == "__main__":
    unittest.main()
