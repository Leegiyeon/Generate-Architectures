"""10개 대표 저장소의 AWS 참조 설계 골든 회귀 검사 — 실제 앱 코드 실행 없음.

검증 대상은 관찰 근거/제안 패턴/다이어그램 파일/비용 미산정/승인 대기.
실제 계정 IAM/보안·실측 처리량·브라우저 시각 QA는 수행하지 않습니다.
"""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree

from scripts.recommend_architecture import run


CASES = (
    {
        "id": "01-vite-static",
        "expected": "static",
        "files": {
            "vite.config.ts": "export default {}\n",
            "src/index.ts": "export function greet(){return 'hello'}\n",
        },
        "needs_rds": False, "needs_db_hint": False,
    },
    {
        "id": "02-next-static-export",
        "expected": "static",
        "files": {
            "package.json": json.dumps({"dependencies":{"next":"15.0.0"}}),
            "next.config.mjs": "export default { output: 'export' };\n",
            "app/page.tsx": "export default function Page(){return <h1>Example</h1>}\n",
        },
        "needs_rds": False,
    },
    {
        "id": "03-next-ssr",
        "expected": "containers",
        "files": {
            "package.json": json.dumps({"dependencies":{"next":"15.0.0"}}),
            "next.config.mjs": "export default {};\n",
            "app/page.tsx": "export default function Page(){return <h1>Server</h1>}\n",
        },
        "requirements": {"rendering_mode":"ssr","environment":"production",
                         "peak_rps":100,"availability_target_percent":99.9},
        "needs_rds": False,
    },
    {
        "id": "04-fastapi-route",
        "expected": "containers",
        "files": {
            "Dockerfile": "FROM python:3.12\n",
            "pyproject.toml": "[project]\nname='fastapi-sample'\n",
            "app/main.py": "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health():\n    return {'ok':True}\n",
        },
        "min_routes": 1, "needs_rds": False,
    },
    {
        "id": "05-nestjs-api",
        "expected": "containers",
        "files": {
            "Dockerfile": "FROM node:22\n",
            "package.json": json.dumps({"dependencies":{"@nestjs/core":"^10.0.0","@nestjs/common":"^10.0.0"}}),
            "src/app.controller.ts": "import { Controller, Get } from '@nestjs/common';\n@Controller('health')\nexport class AppController { @Get() health(){ return 'ok'; } }\n",
        },
        "needs_rds": False,
    },
    {
        "id": "06-prisma-postgres",
        "expected": "containers",
        "files": {
            "Dockerfile": "FROM node:22\n",
            "package.json": json.dumps({"dependencies":{"@prisma/client":"^5","pg":"^8"}}),
            "prisma/schema.prisma": 'datasource db { provider = "postgresql" }\nmodel Person {\n id Int @id\n}\n',
        },
        "needs_rds": True, "needs_db_hint": True,
    },
    {
        "id": "07-mongodb-backend",
        "expected": "containers",
        "files": {
            "Dockerfile": "FROM node:22\n",
            "package.json": json.dumps({"dependencies":{"mongoose":"^8"}}),
            "src/server.js": "const express=require('express');const app=express();app.get('/health',(req,res)=>res.send('ok'));\n",
        },
        "needs_rds": False, "needs_db_hint": True,
        "document_migration_blocked": True,
    },
    {
        "id": "08-serverless-python",
        "expected": "serverless",
        "files": {
            "pyproject.toml": "[project]\nname='handler'\n",
            "serverless.yml": "service: handler\nprovider:\n  name: aws\n  runtime: python3.12\n",
            "handler.py": "def handler(event, context):\n    return {'statusCode':200}\n",
        },
        "needs_rds": False,
    },
    {
        "id": "09-expo-mobile",
        "expected": "mobile",
        "files": {
            "app.json": json.dumps({"expo":{"name":"sample","slug":"sample"}}),
            "package.json": json.dumps({"dependencies":{"expo":"~52.0.0"}}),
            "src/index.ts": "export function hello(){return 42}\n",
        },
        "requirements":{"requires_authentication":False},
        "needs_rds": False,
        "must_not_node":"cognito",
    },
    {
        "id": "10-operational-host-control",
        "expected": "containers",
        "files": {
            "Dockerfile": "FROM python:3.12\n",
            "pyproject.toml": "[project]\nname='host-control'\n",
        },
        "requirements":{
            "requires_host_control":True, "environment":"production",
            "data_classification":"sensitive", "peak_rps":500,
            "operations_preference":"high_availability",
            "rto_minutes":120,"rpo_minutes":30,
        },
        "needs_rds": False,
        "must_block": True,
    },
)


class LinkScanner(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self.script_tags=0
    def handle_starttag(self, tag, attrs):
        if tag=="script":
            self.script_tags+=1
        for name,value in attrs:
            if name=="href" and value:
                self.links.append(value)


class GoldenProjectTests(unittest.TestCase):
    def test_all_ten_synthetic_repositories_end_to_end(self):
        self.assertEqual(len(CASES),10)
        for case in CASES:
            with self.subTest(case=case["id"]), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/"app"
                root.mkdir()
                for rel,content in case["files"].items():
                    path=root/rel
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text(content,encoding="utf-8")
                requirement_path=None
                if case.get("requirements"):
                    requirement_path="requirements.json"
                    (root/requirement_path).write_text(
                        json.dumps(case["requirements"]),encoding="utf-8")
                out=Path(tmp)/"report"
                result=run(root,out,requirements_file=requirement_path)
                self.assertEqual(result["option_id"],case["expected"])
                self.assertFalse(result["user_report"]["production_ready"])
                self.assertFalse(result["decision_record"]["approved"])
                self.assertFalse(result["operations_plan"]["production_ready"])
                self.assertIsNone(result["cost_estimate"]["monthly_total_usd"])
                self.assertEqual(result["cost_estimate"]["status"],"needs_input")

                # 골든 기대값: 실제 운영 DB 발견이 아니라 정적 코드/설정 단서의 유무입니다.
                topology=json.loads((out/"aws-topology.json").read_text(encoding="utf-8"))
                node_ids={x["id"] for x in topology["nodes"]}
                self.assertEqual("rds" in node_ids,case["needs_rds"])
                if case.get("must_not_node"):
                    self.assertNotIn(case["must_not_node"],node_ids)
                if case.get("needs_db_hint"):
                    profile=json.loads((out/"repository-analysis.json").read_text(encoding="utf-8"))
                    self.assertTrue(profile["signals"]["relational_database"] or
                                    profile["signals"]["document_database"])
                if case.get("document_migration_blocked"):
                    db=json.loads((out/"data-access-decision.json").read_text(encoding="utf-8"))
                    self.assertFalse(db["migration_approved_for_automatic_change"])
                if case.get("must_block"):
                    self.assertEqual(result["decision_matrix"]["status"],"blocked_for_review")
                    self.assertEqual(result["validation"]["decision_gate"],"blocked")
                if case.get("min_routes"):
                    self.assertGreaterEqual(result["application_graph"]["nodes"].get("route",0),
                                            case["min_routes"])

                # 한글, AWS 서비스 아이콘, 링크, PNG/SVG의 구조적 품질 검증.
                for name in ("aws-topology.svg","aws-topology.png",
                             "START-HERE.html","START-HERE.md",
                             "deliverables/02-architecture-decisions.md",
                             "deliverables/03-security-operations.md",
                             "deliverables/04-cost-capacity.md",
                             "artifact-index.json","validation.json"):
                    self.assertTrue((out/name).is_file(),(case["id"],name))
                svg=(out/"aws-topology.svg").read_text(encoding="utf-8")
                root_svg=ElementTree.fromstring(svg)
                self.assertTrue(root_svg.tag.endswith("svg"))
                self.assertIn("viewBox",root_svg.attrib)
                self.assertIn("data:image/png;base64,",svg)
                image=(out/"aws-topology.png").read_bytes()
                self.assertEqual(image[:8],bytes([137,80,78,71,13,10,26,10]))
                width,height=struct.unpack(">II",image[16:24])
                self.assertTrue(100<=width<=32000 and 100<=height<=32000,
                                (case["id"],width,height))
                page=(out/"START-HERE.html").read_text(encoding="utf-8")
                self.assertIn("AWS 아키텍처 설계 검토",page)
                self.assertIn("실제",page)
                self.assertIn("승인 전",page)
                scanner=LinkScanner()
                scanner.feed(page)
                self.assertFalse(scanner.script_tags)
                for ref in scanner.links:
                    self.assertFalse(ref.startswith(("http:","https:","javascript:")))
                    if not ref.startswith("#"):
                        self.assertTrue((out/ref).is_file(),(case["id"],ref))
                manifest=json.loads((out/"artifact-index.json").read_text(encoding="utf-8"))
                for item in manifest["primary_files"]:
                    target=out/item["path"]
                    self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                                     item["sha256"])
                self.assertEqual(manifest["chosen_option"],case["expected"])

    def test_audited_fixture_metadata_unique_and_no_secrets(self):
        ids=[c["id"] for c in CASES]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(c.get("expected") in ("static","serverless",
                                                  "containers","mobile") for c in CASES))
        serialized=json.dumps(CASES,ensure_ascii=False)
        for marker in ("PRIVATE_KEY","AWS_SECRET_ACCESS_KEY","actual_aws_account"):
            self.assertNotIn(marker,serialized)


if __name__=="__main__":
    unittest.main()
