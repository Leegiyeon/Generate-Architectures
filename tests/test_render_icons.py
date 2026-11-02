import tempfile
import unittest
from pathlib import Path

from scripts.recommend_architecture import design
from scripts.render_aws_icons import AWS_ICONS, render_icon_diagram


class IconRendererTests(unittest.TestCase):
    def test_every_reference_pattern_renders_real_service_icons(self):
        examples = [
            ([], "backend", {"API Gateway", "Lambda", "DynamoDB", "CloudWatch"}),
            ([], "mobile", {"Amazon Cognito", "Lambda", "DynamoDB"}),
            ([{"path": "next.config.js", "technology": "Next.js", "category": "web"}],
             "web", {"CloudFront", "S3", "AWS WAF"}),
            ([{"path": "Dockerfile", "technology": "Docker", "category": "containers"}],
             "web", {"Application Load Balancer", "ECS Fargate", "Amazon RDS"}),
        ]
        for signals, workload, expected in examples:
            with self.subTest(workload=workload, expected=expected):
                architecture = design(signals, workload, None)
                self.assertTrue(expected.issubset(architecture["nodes"]))
                with tempfile.TemporaryDirectory() as tmp:
                    outputs = render_icon_diagram(architecture, tmp)
                    svg = outputs["svg"].read_text(encoding="utf-8")
                    png = outputs["png"].read_bytes()
                    self.assertIn("data:image/png;base64,", svg)
                    self.assertTrue(png.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10])))
                    self.assertTrue(all(x.stat().st_size > 100 for x in outputs.values()))
                    for node in expected:
                        self.assertIn(node, AWS_ICONS)

    def test_reject_unsupported_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Unsupported service"):
                render_icon_diagram({"nodes": ["NotAService"], "edges": [],
                                     "pattern": "invalid"}, tmp)

    def test_reject_invalid_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unknown node"):
                render_icon_diagram({"nodes": ["User"], "edges": [("User", "S3")],
                                     "pattern": "invalid"}, tmp)


if __name__ == "__main__":
    unittest.main()
