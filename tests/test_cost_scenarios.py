"""Issue #15: 세 가지 사용자 제공 사용량, 단가·리전·구성 누락과 backward compatibility."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.cost_estimator import read_cost_inputs, estimate_costs, markdown_cost
from scripts.cost_scenarios import correlate_topology_costs
from scripts.recommend_architecture import run


def item(name="alb_hour",service="alb",unit="Hrs",price="0.1234",
         minimum=100,baseline=200,peak=300):
    rate = ({"kind":"manual_quote","unit_price_usd":price,
             "source":"https://aws.amazon.com/elasticloadbalancing/pricing/",
             "as_of":"2026-11-03"} if price is not None else {"kind":"unknown"})
    return {"id":name,"service":service,"unit":unit,
            "quantities":{"minimum":minimum,"baseline":baseline,"peak":peak},
            "rate":rate}


def validate_file(root, document):
    (root/"cost.json").write_text(json.dumps(document),encoding="utf-8")
    return read_cost_inputs(root,"cost.json")


class CostScenarioTests(unittest.TestCase):
    def test_three_user_quantities_times_same_provenanced_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=validate_file(Path(tmp), {"schema_version":"2.0","region":"ap-northeast-2",
                                          "items":[item()]})
            r=estimate_costs(cfg)
            self.assertEqual(r["schema_version"],"2.0")
            self.assertEqual(r["scenarios"]["minimum"]["monthly_total_usd"],"12.3400")
            self.assertEqual(r["scenarios"]["baseline"]["monthly_total_usd"],"24.6800")
            self.assertEqual(r["scenarios"]["peak"]["monthly_total_usd"],"37.0200")
            self.assertEqual(r["monthly_total_usd"],"24.6800")
            self.assertEqual(r["quantities_source"],"user_provided_per_scenario")
            self.assertIn("피크",markdown_cost(r))

    def test_missing_one_price_no_fabricated_total_in_any_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                         "items":[item(),item("ecs","ecs_fargate",price=None)]})
            r=estimate_costs(cfg)
            for name in ("minimum","baseline","peak"):
                self.assertIsNone(r["scenarios"][name]["monthly_total_usd"])
                self.assertEqual(r["scenarios"][name]["unpriced_count"],1)
                self.assertIsNotNone(r["scenarios"][name]["priced_subtotal_usd"])
            self.assertIsNone(r["monthly_total_usd"])
            self.assertFalse(r["complete"])

    def test_missing_all_rates_does_not_claim_zero_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                         "items":[item(price=None)]})
            r=estimate_costs(cfg)
            self.assertIsNone(r["monthly_total_usd"])
            self.assertIsNone(r["scenarios"]["baseline"]["priced_subtotal_usd"])

    def test_aws_price_list_looked_up_once_for_all_three_scenarios(self):
        class Client:
            def __init__(self): self.calls=[]
            def get_products(self, **kwargs):
                self.calls.append(kwargs)
                return {"PriceList":[json.dumps({
                    "product":{"attributes":{"regionCode":"ap-northeast-2"}},
                    "terms":{"OnDemand":{"term":{"priceDimensions":{
                        "dim":{"unit":"Requests","beginRange":"0","endRange":"Inf",
                               "pricePerUnit":{"USD":"0.0000002"}}}}}},
                })]}
        one = item("requests","lambda",unit="Requests",price=None,
                   minimum=100000,baseline=1000000,peak=5000000)
        one["rate"]={"kind":"aws_price_list","service_code":"AWSLambda",
                     "filters":{"group":"AWS-Lambda-Requests"}}
        with tempfile.TemporaryDirectory() as tmp:
            cfg=validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                         "items":[one]})
            client=Client()
            disabled=estimate_costs(cfg,live=False,client=client)
            self.assertIsNone(disabled["monthly_total_usd"])
            self.assertFalse(client.calls)
            enabled=estimate_costs(cfg,live=True,client=client)
            self.assertEqual(len(client.calls),1)
            self.assertEqual(enabled["scenarios"]["minimum"]["monthly_total_usd"],"0.0200000")
            self.assertEqual(enabled["scenarios"]["baseline"]["monthly_total_usd"],"0.2000000")
            self.assertEqual(enabled["scenarios"]["peak"]["monthly_total_usd"],"1.0000000")

    def test_input_validation_rejects_guessy_missing_invalid_rates_and_quantities(self):
        base=item()
        examples=[
            {**base,"quantities":{"baseline":10,"peak":20}},
            {**base,"quantities":{"minimum":20,"baseline":10,"peak":30}},
            {**base,"quantities":{"minimum":True,"baseline":20,"peak":30}},
            {**base,"quantities":{"minimum":-1,"baseline":20,"peak":30}},
            {**base,"quantities":{"minimum":float("nan"),"baseline":20,"peak":30}},
            {**base,"service":"unknown_service"},
            {**base,"rate":{"kind":"manual_quote","unit_price_usd":0.1,
                            "source":"https://not-aws.example.com","as_of":"2026-11-03"}},
        ]
        for bad in examples:
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                             "items":[bad]})

    def test_duplicate_service_id_and_region_mismatch_remain_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                         "items":[item(),item()]})
            cfg=validate_file(Path(tmp),{"schema_version":"2.0","region":"ap-northeast-2",
                                         "items":[item()]})
            report=estimate_costs(cfg)
            topology={"region":"us-east-1","nodes":[
                {"id":"client"},{"id":"aws"},{"id":"alb"},{"id":"task_a"},{"id":"observability"}
            ]}
            report=correlate_topology_costs(report,topology,{})
            self.assertEqual(report["topology_coverage"]["status"],"region_mismatch")
            self.assertFalse(report["pricing_applicable_to_selected_region"])
            self.assertFalse(report["complete_for_entire_architecture"])
            self.assertIn("ecs_fargate",report["topology_coverage"]["missing_categories"])

    def test_full_pipeline_offline_comparison_does_not_invent_other_aws_charges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            cfg={"schema_version":"2.0","region":"ap-northeast-2","items":[
                item("alb","alb",minimum=100,baseline=200,peak=250),
                item("ecs","ecs_fargate",price=None,minimum=100,baseline=200,peak=250),
            ]}
            (root/"cost.json").write_text(json.dumps(cfg),encoding="utf-8")
            (root/"requirements.json").write_text(json.dumps({"region":"ap-northeast-2",
                                                                "peak_rps":200}),encoding="utf-8")
            out=Path(tmp)/"output"
            result=run(root,out,requirements_file="requirements.json",cost_input="cost.json")
            self.assertEqual(result["option_id"],"containers")
            cost=json.loads((out/"cost-estimate.json").read_text(encoding="utf-8"))
            self.assertIsNone(cost["monthly_total_usd"])
            self.assertEqual(cost["scenarios"]["minimum"]["unpriced_count"],1)
            self.assertEqual(cost["scenarios"]["baseline"]["unpriced_count"],1)
            self.assertEqual(cost["scenarios"]["peak"]["unpriced_count"],1)
            self.assertIn("data_transfer",cost["topology_coverage"]["missing_categories"])
            self.assertIn("cloudwatch_logs",cost["topology_coverage"]["missing_categories"])
            md=(out/"deliverables/04-cost-capacity.md").read_text(encoding="utf-8")
            page=(out/"START-HERE.html").read_text(encoding="utf-8")
            self.assertIn("최소 / 기준 / 피크",md)
            self.assertIn("사용자 입력 최소·기준·피크",page)
            self.assertIn("To-Be 비용 분류 누락",page)
            self.assertNotIn("전체 AWS 청구액임",page)
            self.assertFalse(cost["complete_for_entire_architecture"])

    def test_legacy_cost_input_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg=validate_file(root,{"region":"ap-northeast-2",
                                    "items":[{"id":"sample","quantity":10,"unit":"GB",
                                              "rate":{"kind":"unknown"}}]})
            report=estimate_costs(cfg)
            self.assertNotIn("scenarios",report)
            self.assertEqual(report["status"],"partial_unpriced")
            self.assertIsNone(report["monthly_total_usd"])


if __name__ == "__main__":
    unittest.main()
