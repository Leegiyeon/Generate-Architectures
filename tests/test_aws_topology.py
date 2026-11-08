"""AWS 상세 To-Be 토폴로지: 영역·서비스 연결·가정의 정합성을 검증합니다."""
import json
import html
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from scripts.architecture_advisor import decide
from scripts.aws_topology import design_aws_topology, markdown_topology
from scripts.evidence_contract import build_evidence_contract
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run
from scripts.render_aws_topology import SERVICE_ICONS, render_aws_topology


def case(files, supplied=None):
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    for path, data in files.items():
        file = root / path
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(data,encoding="utf-8")
    data = supplied or {}
    requirements = parse_requirements(None, root)
    requirements.update(data)
    profile = inspect_repository(root)
    architecture = decide(profile,requirements)
    contract = build_evidence_contract(profile,{"nodes":[],"edges":[]},requirements,data.keys(),architecture)
    topology = design_aws_topology(architecture,profile,requirements,contract)
    return temp, architecture, topology


class AWSTopologyTests(unittest.TestCase):
    def test_static_is_global_delivery_without_invented_vpc(self):
        tmp, architecture, topo = case({"vite.config.ts":"export default {}"})
        try:
            self.assertEqual(architecture["option_id"], "static")
            nodes={x["id"] for x in topo["nodes"]}
            self.assertIn("cdn",nodes)
            self.assertIn("bucket",nodes)
            self.assertIn("oac",nodes)
            self.assertNotIn("vpc",nodes)
            self.assertTrue(all(x["status"] == "proposed_not_deployed" for x in topo["nodes"]))
            self.assertTrue(any(x["source"]=="cdn" and x["target"]=="bucket" for x in topo["edges"]))
            self.assertNotIn("ALB",markdown_topology(topo))
        finally:
            tmp.cleanup()

    def test_serverless_lambda_without_unnecessary_vpc(self):
        tmp,architecture,topo=case({"pyproject.toml":"[project]\nname='api'\n"})
        try:
            self.assertEqual(architecture["option_id"], "serverless")
            nodes={x["id"] for x in topo["nodes"]}
            self.assertIn("lambda",nodes)
            self.assertIn("api",nodes)
            self.assertNotIn("vpc",nodes)
            self.assertNotIn("dynamodb",nodes)
            self.assertIn("NET-SERVERLESS",{x["id"] for x in topo["review_required"]})
        finally:tmp.cleanup()

    def test_container_ha_rds_span_two_symbolic_azs(self):
        tmp, architecture, topo = case({
            "Dockerfile": "FROM node:22",
            "package.json": json.dumps({"dependencies":{"pg":"*"}}),
        },{
            "workload":"backend", "requires_relational_database":True,
            "region":"ap-northeast-2", "availability_target_percent":99.95,
            "operations_preference":"high_availability",
        })
        try:
            self.assertEqual(architecture["option_id"],"containers")
            ids={x["id"] for x in topo["nodes"]}
            for item in ("vpc","public_a","public_b","app_a","app_b","db_a",
                         "db_b","task_a","task_b","rds","rds_standby","db_subnet_group"):
                self.assertIn(item,ids)
            self.assertTrue(topo["high_availability_proposed"])
            self.assertEqual(topo["symbolic_azs"],["AZ-A","AZ-B"])
            self.assertTrue(topo["region_confirmed"])
            self.assertTrue(any(x["source"]=="rds" and x["target"]=="rds_standby"
                                and x["kind"]=="replication" for x in topo["edges"]))
            self.assertTrue(all(x["source"] in ids and x["target"] in ids for x in topo["edges"]))
            self.assertIn("NET-PRIVATE-EGRESS",{x["id"] for x in topo["review_required"]})
            self.assertNotIn("prod_access_key",json.dumps(topo))
        finally:tmp.cleanup()

    def test_container_without_db_keeps_two_public_subnets_but_no_rds(self):
        tmp, architecture, topo=case({"Dockerfile":"FROM python:3.12"})
        try:
            ids={x["id"] for x in topo["nodes"]}
            self.assertIn("alb",ids)
            self.assertTrue({"public_a","public_b","app_a","app_b"}.issubset(ids))
            self.assertIn("task_a",ids)
            self.assertNotIn("task_b",ids)
            self.assertNotIn("rds",ids)
            self.assertFalse(topo["high_availability_proposed"])
            self.assertFalse(topo["region_confirmed"])
        finally:tmp.cleanup()

    def test_mobile_no_auth_excludes_cognito(self):
        tmp, architecture, topo=case({"app.json":"{}"},{"requires_authentication":False})
        try:
            self.assertEqual(architecture["option_id"],"mobile")
            ids={x["id"] for x in topo["nodes"]}
            self.assertNotIn("cognito",ids)
            self.assertIn("lambda",ids)
            self.assertNotIn("vpc",ids)
        finally:tmp.cleanup()

    def test_static_explicit_ssr_is_flagged(self):
        tmp, architecture, topo=case({
            "package.json":json.dumps({"dependencies":{"next":"15"}}),
            "next.config.js":"module.exports = {output:'export'}",
        },{"workload":"web","rendering_mode":"ssr"})
        try:
            self.assertEqual(architecture["option_id"],"static")
            self.assertIn("NET-SSR-CONFLICT",{x["id"] for x in topo["review_required"]})
        finally:tmp.cleanup()

    def test_graphviz_keeps_boundaries_and_rendered_svg_png(self):
        tmp, architecture, topo=case({"Dockerfile":"FROM python:3.12"})
        try:
            with tempfile.TemporaryDirectory() as out:
                paths=render_aws_topology(topo,out)
                self.assertTrue(paths["png"].read_bytes().startswith(bytes([137,80,78,71])))
                svg=paths["svg"].read_text(encoding="utf-8")
                dot=paths["dot"].read_text(encoding="utf-8")
                self.assertIn("cluster",dot)
                self.assertIn("VPC",svg)
                self.assertIn("AZ-A", html.unescape(svg))
                ns = {"svg": "http://www.w3.org/2000/svg"}
                client = next(group for group in ET.fromstring(svg).findall(".//svg:g", ns)
                              if group.findtext("svg:title", namespaces=ns) == "node_0")
                icon = client.find("svg:image", ns)
                label = client.find("svg:text", ns)
                self.assertIsNotNone(icon)
                self.assertIsNotNone(label)
                self.assertIn("사용자", label.text)
                # 라벨의 baseline이 아이콘 아래에 충분히 떨어져 있어야 합니다.
                self.assertGreater(float(label.attrib["y"]),
                                   float(icon.attrib["y"]) +
                                   float(icon.attrib["height"].removesuffix("px")) + 10)
        finally:tmp.cleanup()

    def test_integration_retains_both_original_and_detailed_architecture_diagrams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12",encoding="utf-8")
            output=Path(tmp)/"output"
            result=run(root,output)
            for name in ("architecture.svg","architecture.png",
                         "aws-topology.svg","aws-topology.png","aws-topology.dot",
                         "aws-topology.json","aws-topology.md"):
                self.assertTrue((output/name).is_file(),name)
            self.assertEqual(result["aws_topology"]["status"],"proposed_unverified")
            doc=json.loads((output/"aws-topology.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["pattern"],"containers")
            self.assertIn("NET-PRIVATE-EGRESS",{x["id"] for x in doc["review_required"]})

    def test_every_service_label_is_below_its_icon(self):
        identifiers = [*SERVICE_ICONS, "task_a", "task_b"]
        topology = {"nodes": [{"id": ident, "kind": "compute", "parent": None,
                               "name": f'{ident} <후보> & "확인 필요"'}
                              for ident in identifiers], "edges": []}
        with tempfile.TemporaryDirectory() as out:
            paths = render_aws_topology(topology, out)
            root = ET.parse(paths["svg"]).getroot()
            ns = {"svg": "http://www.w3.org/2000/svg"}
            groups = [group for group in root.findall(".//svg:g", ns)
                      if group.attrib.get("class") == "node"]
            self.assertEqual(len(groups), len(identifiers))
            for group, ident in zip(groups, identifiers):
                with self.subTest(service=ident):
                    icon = group.find("svg:image", ns)
                    label = group.find("svg:text", ns)
                    self.assertIsNotNone(icon)
                    self.assertIsNotNone(label)
                    self.assertEqual(label.text, f'{ident} <후보> & "확인 필요"')
                    bottom = float(icon.attrib["y"]) + float(icon.attrib["height"].removesuffix("px"))
                    self.assertGreater(float(label.attrib["y"]) - float(label.attrib["font-size"]),
                                       bottom + 2)


if __name__=="__main__":
    unittest.main()
