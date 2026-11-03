"""제품 실행 정책 회귀 검사: 자동 CI와 사용자 요청 설계를 분리."""
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
        # Actions 분석·업로드 단계 양쪽 모두 수동 이벤트에서만 실행되어야 합니다.
        for step in ("설계 분석 및 다이어그램 생성 (수동 실행)",
                     "생성 파일 업로드 (수동 실행)"):
            pattern = r"- name: " + re.escape(step) + r"\n\s*if: github.event_name == 'workflow_dispatch'"
            self.assertRegex(workflow, pattern)
        # PR 댓글용 쓰기 권한은 기본 워크플로에서 필요하지 않습니다.
        self.assertNotIn("pull-requests: write", workflow)
        self.assertIn("contents: read", workflow)

    def test_external_default_is_manual_and_pr_is_separate_opt_in(self):
        base = (ROOT / "examples/aws-architecture.yml").read_text(encoding="utf-8")
        opt = (ROOT / "examples/aws-architecture-pr-optional.yml").read_text(encoding="utf-8")
        self.assertRegex(base, r"(?m)^  workflow_dispatch:")
        self.assertNotRegex(base, r"(?m)^  pull_request:")
        self.assertRegex(opt, r"(?m)^  pull_request:")
        self.assertIn('enable_ai: "false"', opt)
        self.assertIn('live_pricing: "false"', opt)
        self.assertNotIn("id-token: write", opt)

    def test_product_boundaries_and_user_steps_are_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        product = (ROOT / "docs/PRODUCT.md").read_text(encoding="utf-8")
        self.assertIn("## 30초 사용 안내", readme)
        for key in ("저장소", "Run workflow", "Artifacts", "Local AWS Inspector"):
            self.assertIn(key, readme)
        for key in ("미구현", "현재 제공", "AWS 자동", "최초 1회", "수동"):
            self.assertIn(key, product)
        # 고가치 미래 산출물을 '현재 구현'으로 과장하지 않음
        self.assertIn("상세 VPC/Subnet/AZ 구축 설계가 아니라", readme)
        self.assertIn("현재는 4종 후보 비교", product)


if __name__ == "__main__":
    unittest.main()
