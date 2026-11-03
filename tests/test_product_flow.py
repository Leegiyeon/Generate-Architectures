"""제품 실행 정책: 자동 테스트 vs 수동 분석, 2개 목적 선택과 최소 입력 UX."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ProductFlowTests(unittest.TestCase):
    def test_ci_retains_push_and_pr_tests_but_manual_design_only(self):
        workflow = (ROOT / ".github/workflows/aws-architecture-recommendation.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"(?m)^on:")
        self.assertRegex(workflow, r"(?m)^  push:")
        self.assertRegex(workflow, r"(?m)^  pull_request:")
        self.assertRegex(workflow, r"(?m)^  workflow_dispatch:")
        self.assertIn("python3 -m unittest discover -s tests -v", workflow)
        for step in ("설계 분석 및 다이어그램 생성 (수동 실행)",
                     "생성 파일 업로드 (수동 실행)"):
            self.assertRegex(
                workflow,
                r"- name: " + re.escape(step) + r"\n\s*if: github.event_name == 'workflow_dispatch'",
            )
        self.assertIn("contents: read", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertIn("analysis_goal:", workflow)
        self.assertIn("options: [new_aws, migrate_onprem]", workflow)

    def test_external_workflow_requires_only_goal_and_uploads_html(self):
        basic = (ROOT / "examples/aws-architecture.yml").read_text(encoding="utf-8")
        advanced = (ROOT / "examples/aws-architecture-pr-optional.yml").read_text(encoding="utf-8")
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        self.assertRegex(basic, r"(?m)^  workflow_dispatch:")
        self.assertNotRegex(basic, r"(?m)^  pull_request:")
        self.assertIn("options:", basic)
        self.assertIn("          - new_aws", basic)
        self.assertIn("          - migrate_onprem", basic)
        self.assertIn("analysis_goal: ${{ inputs.analysis_goal }}", basic)
        self.assertIn("aws-architecture-recommendation", basic)
        self.assertNotIn("OPENAI_API_KEY", basic)
        self.assertNotIn("live_pricing:", basic)
        self.assertNotIn("id-token: write", basic)
        self.assertIn('enable_ai: "false"', advanced)
        self.assertIn('live_pricing: "false"', advanced)
        self.assertIn("analysis_goal:", action)
        self.assertIn('default: new_aws', action)
        self.assertIn("--analysis-goal", action)

    def test_entrypoint_docs_are_short_and_honest_about_migration(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        product = (ROOT / "docs/PRODUCT.md").read_text(encoding="utf-8")
        self.assertIn("## 30초 사용 안내", readme)
        self.assertLess(len(readme), 5000)
        for word in ("Run workflow", "Artifacts", "START-HERE.html",
                     "migrate_onprem", "new_aws", "Local AWS Inspector"):
            self.assertIn(word, readme)
        for word in ("미구현", "현재 지원", "수동", "온프레미스", "AWS"):
            self.assertIn(word, product)
        self.assertIn("상세 논리 설계 제안", readme)
        self.assertIn("실제 계정 구성이나 구축 검증 결과는 아닙니다", readme)
        self.assertIn("AWS 자원", product)


if __name__ == "__main__":
    unittest.main()
