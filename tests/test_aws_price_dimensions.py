"""AWS Price List 공개 요금 구조를 모사한 단일 SKU/계층형 가격 회귀 테스트.

AWS 공개 문서의 OnDemand/priceDimensions/beginRange/endRange 규칙을 기반으로
가상값을 사용하며 실제 AWS 단가·계정/할인/무료 한도를 주장하지 않습니다.
"""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.aws_price_dimensions import interpret_price_dimensions, amount_for_tiers
from scripts.cost_estimator import estimate_costs, read_cost_inputs, markdown_cost


def price_product(ranges, *, sku="SIMULATEDSKU01", region="ap-northeast-2",
                  unit="Requests", term_attrs=None):
    dimensions={}
    for i,(begin,end,rate) in enumerate(ranges):
        dimensions[f"dim{i}"]={
            "unit":unit, "beginRange":str(begin), "endRange":str(end),
            "pricePerUnit":{"USD":str(rate)}, "appliesTo":[],
        }
    return {"product":{"sku":sku,"attributes":{"regionCode":region}},
            "terms":{"OnDemand":{
                sku+".JRTCKXETXF":{
                    "priceDimensions":dimensions,
                    "effectiveDate":"2026-11-01T00:00:00Z",
                    "termAttributes":term_attrs if term_attrs is not None else {},
                }
            }}}


def response(ranges, **kwargs):
    return {"PriceList":[json.dumps(price_product(ranges,**kwargs))]}


def input_v2(rate, *, q=(50,150,300)):
    return {"schema_version":"2.0","region":"ap-northeast-2","items":[{
        "id":"simulated_request","service":"lambda","unit":"Requests",
        "quantities":{"minimum":q[0],"baseline":q[1],"peak":q[2]},
        "rate":rate,
    }]}


AWS_LOOKUP={
    "kind":"aws_price_list",
    "service_code":"AWSLambda",
    "filters":{"group":"AWS-Lambda-Requests"},
}


class FakePricingClient:
    def __init__(self, result):
        self.result=result
        self.calls=[]
    def get_products(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class AWSPriceTierTests(unittest.TestCase):
    def test_one_sku_contiguous_graduated_tiers_arithmetic(self):
        client=FakePricingClient(response([
            ("0","100","0.2"),("100","Inf","0.1"),
        ]))
        r=estimate_costs(input_v2(AWS_LOOKUP),live=True,client=client)
        self.assertEqual(len(client.calls),1)
        for key,value in [("minimum","10.0"),("baseline","25.0"),("peak","40.0")]:
            self.assertEqual(r["scenarios"][key]["monthly_total_usd"],value)
        self.assertEqual(r["monthly_total_usd"],"25.0")
        line=r["scenarios"]["baseline"]["lines"][0]
        self.assertEqual(line["price_model"],"tiered_graduated")
        self.assertIsNone(line["unit_price_usd"])
        self.assertEqual(line["sku"],"SIMULATEDSKU01")
        self.assertEqual(line["price_effective_date"],"2026-11-01T00:00:00Z")
        self.assertEqual(line["tier_schedule"],[
            {"begin":"0","end":"100","usd_per_unit":"0.2"},
            {"begin":"100","end":"Inf","usd_per_unit":"0.1"},
        ])
        self.assertIn("2026-11-01",markdown_cost(r))
        self.assertIn("계층 가격",markdown_cost(r))
        self.assertEqual(client.calls[0]["ServiceCode"],"AWSLambda")
        f={x["Field"]:x["Value"] for x in client.calls[0]["Filters"]}
        self.assertEqual(f["regionCode"],"ap-northeast-2")

    def test_boundary_zero_and_three_tiers_without_floating_point_rounding(self):
        dims=[("0","10","0.20"),("10","100","0.10"),("100","Inf","0.05")]
        parsed=interpret_price_dimensions(response(dims),"Requests","ap-northeast-2")
        self.assertEqual(parsed["status"],"priced")
        self.assertEqual(str(amount_for_tiers(parsed["tiers"],"0")),"0.00")
        self.assertEqual(str(amount_for_tiers(parsed["tiers"],"10")),"2.00")
        self.assertEqual(str(amount_for_tiers(parsed["tiers"],"110")),"11.50")

    def test_flat_single_sku_keeps_existing_v2_behavior(self):
        client=FakePricingClient(response([("0","Inf","0.0000002")]))
        r=estimate_costs(input_v2(AWS_LOOKUP,q=(100000,1000000,5000000)),
                         live=True,client=client)
        self.assertEqual(r["scenarios"]["baseline"]["monthly_total_usd"],"0.2000000")
        self.assertEqual(r["scenarios"]["peak"]["monthly_total_usd"],"1.0000000")
        self.assertEqual(r["lines"][0]["price_model"],"flat")
        self.assertEqual(len(client.calls),1)

    def test_all_ambiguous_rate_structures_fail_closed(self):
        standard=[("0","100","0.2"),("100","Inf","0.1")]
        bad=[]
        bad.append({"PriceList":[json.dumps(price_product(standard)),
                                 json.dumps(price_product(standard,sku="SECOND"))]})
        bad.append({**response(standard),"NextToken":"NEXT"})
        bad.append(response([("0","100","0.2"),("120","Inf","0.1")]))  # gap
        bad.append(response([("0","100","0.2"),("90","Inf","0.1")]))  # overlap
        bad.append(response([("0","100","0.2")]))                       # partial
        bad.append(response([("1","Inf","0.2")]))                       # missing zero
        bad.append(response(standard,region="us-east-1"))              # wrong region
        bad.append(response(standard,unit="GB"))                       # wrong unit
        bad.append(response(standard,term_attrs={"contract":"special"}))
        bad.append(response(standard,sku="INVALID SKU VALUE"))
        for dim_mutation in (
            lambda d: d.update(appliesTo=["REGION-WIDE-FREETIER"]),
            lambda d: d.update(pricePerUnit={"EUR":"0.2"}),
            lambda d: d.update(pricePerUnit={"USD":"NaN"}),
            lambda d: d.update(pricePerUnit={"USD":"-0.2"}),
        ):
            obj=price_product(standard)
            dim_mutation(next(iter(next(iter(obj["terms"]["OnDemand"].values()))
                                   ["priceDimensions"].values())))
            bad.append({"PriceList":[obj]})
        for x in bad:
            with self.subTest(value=x):
                result=interpret_price_dimensions(x,"Requests","ap-northeast-2")
                self.assertEqual(result["status"],"unpriced")
                self.assertFalse(result["tiers"])
        self.assertEqual(interpret_price_dimensions({"PriceList":["{broken"]},
                                                     "Requests","ap-northeast-2")["status"],
                         "unpriced")

    def test_pricelist_failure_returns_no_secret_raw_response(self):
        class Broken:
            def get_products(self, **kwargs):
                raise ValueError("AWS_SECRET_ACCESS_KEY=DO_NOT_ECHO")
        r=estimate_costs(input_v2(AWS_LOOKUP),live=True,client=Broken())
        self.assertIsNone(r["monthly_total_usd"])
        self.assertEqual(r["unpriced_count"],1)
        self.assertNotIn("DO_NOT_ECHO",json.dumps(r))

    def test_old_v1_tiered_rate_is_still_unpriced_without_contract_break(self):
        class Client:
            def get_products(self, **kwargs):
                return response([("0","100","0.2"),("100","Inf","0.1")])
        old={"region":"ap-northeast-2","items":[{
            "id":"requests","quantity":150,"unit":"Requests","rate":AWS_LOOKUP,
        }]}
        r=estimate_costs(old,live=True,client=Client())
        self.assertNotIn("scenarios",r)
        self.assertIsNone(r["monthly_total_usd"])
        self.assertEqual(r["lines"][0]["status"],"unpriced")

    def test_no_external_lookup_without_opt_in_even_for_tiered_input(self):
        client=FakePricingClient(response([("0","100","0.2"),("100","Inf","0.1")]))
        r=estimate_costs(input_v2(AWS_LOOKUP),live=False,client=client)
        self.assertFalse(client.calls)
        self.assertIsNone(r["monthly_total_usd"])
        self.assertEqual(r["price_resolution"],"offline_manual_quote_or_unpriced")

    def test_input_validation_still_rejects_bad_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"cost.json").write_text(json.dumps(input_v2(AWS_LOOKUP)))
            config=read_cost_inputs(root,"cost.json")
            self.assertEqual(config["schema_version"],"2.0")
            with self.assertRaises(ValueError):
                read_cost_inputs(root,"../secret.json")


if __name__ == "__main__":
    unittest.main()
