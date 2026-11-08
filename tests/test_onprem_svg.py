"""Valid inventory limits must retain complete labels in separate card rows."""
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from scripts.onprem_inventory import assess_inventory, validate_inventory
from scripts.render_onprem_as_is import render_as_is_svg


NS = {"svg": "http://www.w3.org/2000/svg"}


def maximum_inventory():
    servers = [{
        "id": "w" * 23 + str(i), "role": "unknown", "os": "windows",
        "cpu_cores": 1023.1234567890123,
        "memory_gb": 1048575.123456789,
        "storage_gb": 1073741823.1234567,
        "db_engine": "none", "access": "unknown",
    } for i in range(8)]
    connections = [{"from": servers[i // 4]["id"],
                    "to": servers[4 + i % 4]["id"],
                    "purpose": "application"} for i in range(16)]
    return {"schema_version": "1.0", "servers": servers, "connections": connections}


class OnpremSvgTests(unittest.TestCase):
    def test_maximum_aliases_and_precise_capacities_have_distinct_complete_rows(self):
        report = assess_inventory(validate_inventory(maximum_inventory()), {"signals": {}})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "as-is.svg"
            render_as_is_svg(report, path)
            root = ET.parse(path).getroot()
        cards = root.findall("svg:g[@class='server-card']", NS)
        self.assertEqual(len(cards), 8)
        for server, card in zip(report["servers"], cards):
            labels = card.findall("svg:text", NS)
            text = [node.text for node in labels]
            self.assertEqual(text, [
                "별칭: " + server["id"], "역할: 미확인 / OS: Windows",
                "CPU: " + str(server["cpu_cores"]),
                "RAM: " + str(server["memory_gb"]) + " GB",
                "스토리지: " + str(server["storage_gb"]) + " GB",
                "DB: 없음(사용자 선언)", "접근: 미확인 / 사용자 선언(검증 전)",
            ])
            rect = card.find("svg:rect", NS)
            top, height = float(rect.get("y")), float(rect.get("height"))
            baselines = [float(label.get("y")) for label in labels]
            self.assertTrue(all(top < y < top + height for y in baselines))
            self.assertTrue(all(b - a >= 27 for a, b in zip(baselines, baselines[1:])))
        # Complete maximum-length connection strings stay available after all four card rows.
        direct_text = root.findall("svg:g[@class='declared-connections']/svg:text", NS)
        links = [node for node in direct_text if "  →  " in (node.text or "")]
        self.assertEqual(len(links), 16)
        for edge, label in zip(report["connections"], links):
            self.assertEqual(label.text, edge["from"] + "  →  " + edge["to"] +
                             "   [application]")
            self.assertGreater(float(label.get("y")), top + height)
            self.assertLess(float(label.get("y")), float(root.get("height")))

    def test_missing_inventory_keeps_explicit_unknown_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.svg"
            render_as_is_svg(assess_inventory(None, {}), path)
            root = ET.parse(path).getroot()
        self.assertEqual(root.findall("svg:g[@class='server-card']", NS), [])
        self.assertIn("기존 인프라 미입력", "".join(root.itertext()))
        self.assertIn("연결 미입력", "".join(root.itertext()))


if __name__ == "__main__":
    unittest.main()
