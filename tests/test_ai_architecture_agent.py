"""선택형 AI 아키텍처 검토의 구조화 출력·기본 비활성화·오류 격리 테스트."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ai_architecture_agent import (
    build_context, review_architecture, markdown_ai_review, validate_review,
)
from scripts.architecture_advisor import decide
from scripts.repository_analyzer import inspect_repository
from scripts.requirements_model import parse_requirements
from scripts.recommend_architecture import run


def fixture():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
        profile=inspect_repository(root)
        requirements=parse_requirements(None,root)
        architecture=decide(profile,requirements)
        graph={"counts":{"nodes":{"module":2, "function":5, "route":1, "model":0}},
               "errors":[],"scan_truncated":False}
        return profile, graph, requirements, architecture


def mock_response(ctx, *, option=None, ids=None):
    proposed = option or next(x["option_id"] for x in ctx["options"] if x["applicable"])
    evidence = ids or [ctx["evidence"][0]["id"]]
    return {
        "status":"completed",
        "output":[{"type":"message","content":[{"type":"output_text",
                   "text":json.dumps({
                       "recommended_option":proposed,
                       "decision_summary":"확인된 기술 단서와 운영 요구를 비교한 초기 검토 의견입니다.",
                       "evidence_ids":evidence,
                       "alternatives":[{"option_id":proposed,"tradeoff":"비용 산정과 성능 검증이 필요합니다.","evidence_ids":evidence}],
                       "risks":[{"description":"RTO/RPO 및 보안 설계를 확인해야 합니다.","evidence_ids":[]}],
                       "questions":["예상 최대 동시 요청 수를 알고 계신가요?"]
                   },ensure_ascii=False)}]}]
    }


class AIArchitectureAgentTests(unittest.TestCase):
    def test_disabled_never_calls_transport_or_reads_api_key(self):
        values=fixture()
        result=review_architecture(*values,enabled=False,api_key="fake",
            transport=lambda *_: self.fail("outbound API called without consent"))
        self.assertEqual(result["status"],"disabled")
        self.assertIn("비활성화",markdown_ai_review(result))

    def test_missing_key_does_not_call(self):
        values=fixture()
        result=review_architecture(*values,enabled=True,api_key=None,
            transport=lambda *_: self.fail("outbound API called without key"))
        self.assertEqual(result["status"],"unavailable")

    def test_minimized_payload_and_validated_output(self):
        profile,graph,requirements,architecture=fixture()
        # URL/파일명/함수 식별자/소스 내용은 외부 API 입력에 포함하지 않습니다.
        profile["evidence"]["api_routes"]=["src/private-route-SECRET.ts"]
        profile["signals"]["docker"]=True
        graph["nodes"]=[{"name":"function-CONFIDENTIAL","path":"src/db-secret.py"}]
        original=architecture["option_id"]
        def fake(key,payload):
            self.assertEqual(key,"secret-token-only-for-test")
            self.assertFalse(payload["store"])
            self.assertEqual(payload["text"]["format"]["type"],"json_schema")
            self.assertEqual(payload["text"]["format"]["strict"],True)
            prompt=payload["input"]
            for phrase in ("private-route-SECRET","function-CONFIDENTIAL","src/db-secret.py",
                           "secret-token-only-for-test","Dockerfile"):
                self.assertNotIn(phrase,prompt)
            context=json.loads(prompt)
            self.assertGreater(len(context["evidence"]),2)
            self.assertTrue(all(x["id"].startswith("E") for x in context["evidence"]))
            return mock_response(context)
        result=review_architecture(profile,graph,requirements,architecture,enabled=True,
                                   api_key="secret-token-only-for-test",transport=fake)
        self.assertEqual(result["status"],"reviewed_unverified")
        self.assertEqual(original,architecture["option_id"])
        self.assertIn("검증 전",markdown_ai_review(result))
        self.assertNotIn("private-route-SECRET",json.dumps(result))

    def test_reject_unknown_evidence_id_and_forbidden_option(self):
        p,g,r,a=fixture()
        context=build_context(p,g,r,a)
        bad=mock_response(context)
        decoded=json.loads(bad["output"][0]["content"][0]["text"])
        decoded["evidence_ids"]=["HALLUCINATED"]
        with self.assertRaisesRegex(ValueError,"증거"):
            validate_review(decoded,context)
        decoded["evidence_ids"]=[context["evidence"][0]["id"]]
        not_applicable=next(x["option_id"] for x in context["options"] if not x["applicable"])
        decoded["recommended_option"]=not_applicable
        with self.assertRaisesRegex(ValueError,"검토 불가능"):
            validate_review(decoded,context)

    def test_malformed_or_failed_api_preserves_rule_based_choice(self):
        p,g,r,a=fixture()
        original=a["option_id"]
        responses=[
            lambda *_: {"status":"incomplete","output":[]},
            lambda *_: {"status":"completed","output":[]},
            lambda *_: (_ for _ in ()).throw(OSError("sensitive error response")),
        ]
        for transport in responses:
            got=review_architecture(p,g,r,a,enabled=True,api_key="test",transport=transport)
            self.assertEqual(got["status"],"error")
            self.assertEqual(a["option_id"],original)
            self.assertNotIn("sensitive",json.dumps(got))

    def test_end_to_end_default_off_creates_ai_status_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            (root/"Dockerfile").write_text("FROM python:3.12")
            output=Path(tmp)/"output"
            with patch("scripts.ai_architecture_agent._send_request",
                       side_effect=AssertionError("Unexpected API call")):
                run(root,output)
            result=json.loads((output/"ai-review.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"],"disabled")
            self.assertTrue((output/"ai-review.md").is_file())
            self.assertIn("AI 솔루션 아키텍처 보조 검토",
                          (output/"recommendation.md").read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
