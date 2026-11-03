"""Offline AWS architecture report structural/integrity QA.

This does NOT certify visual appearance, browser layout, architecture suitability or AWS
operation. It audits generated HTML/SVG/PNG structure and source consistency only.
"""
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import struct
from urllib.parse import unquote
from xml.etree import ElementTree


PNG_HEADER = b"\x89PNG\r\n\x1a\n"


class _ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.hrefs = []
        self.images = []
        self.scripts = 0
        self.styles = []
        self._in_style = False
        self.details = 0
        self.summaries = 0
        self.open_details = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "a":
            self.hrefs.append(values.get("href"))
        elif tag == "img":
            self.images.append((values.get("src"), values.get("alt")))
        elif tag == "script":
            self.scripts += 1
        elif tag == "style":
            self._in_style = True
        elif tag == "details":
            self.details += 1
            self.open_details.append(False)
        elif tag == "summary":
            self.summaries += 1
            if not self.open_details:
                raise ValueError("summary는 details 내부에 있어야 합니다.")
            self.open_details[-1] = True

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False
        if tag == "details":
            if not self.open_details or not self.open_details.pop():
                raise ValueError("details에는 접근성 summary가 필요합니다.")

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)


def _safe_local_path(root, href):
    if not href or not isinstance(href, str) or href.startswith(("/", "\\")):
        raise ValueError("링크가 비어 있거나 루트 경로로 지정되었습니다.")
    if "://" in href or href.lower().startswith(("javascript:", "data:", "file:")):
        raise ValueError("외부 URL/실행 가능 링크를 사용자 보고서에 넣을 수 없습니다.")
    if href.startswith("#"):
        return None, href[1:]
    if "#" in href:
        filename, fragment = href.split("#", 1)
    else:
        filename, fragment = href, None
    if "?" in filename:
        raise ValueError("쿼리 스트링 URL은 오프라인 결과물 링크로 지원하지 않습니다.")
    file = (root / unquote(filename)).resolve()
    if not file.is_relative_to(root) or not file.is_file():
        raise ValueError("존재하지 않거나 출력 디렉터리를 벗어나는 보고서 링크: " + href)
    return file, fragment


def _svg(file):
    try:
        root = ElementTree.parse(file).getroot()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError("SVG 열기 또는 XML 파싱 실패: " + str(file.name)) from exc
    if not root.tag.endswith("svg") or not root.attrib.get("viewBox"):
        raise ValueError("SVG 루트와 viewBox가 필요합니다: " + str(file.name))
    viewbox = root.attrib["viewBox"].replace(",", " ").split()
    if len(viewbox) != 4:
        raise ValueError("SVG viewBox는 네 숫자로 구성해야 합니다.")
    try:
        coords = [float(x) for x in viewbox]
    except ValueError:
        raise ValueError("SVG viewBox 좌표를 읽을 수 없습니다.") from None
    if not (0 < coords[2] <= 100000 and 0 < coords[3] <= 100000):
        raise ValueError("SVG viewport가 유효하지 않습니다.")
    return root


def audit_report(folder):
    root = Path(folder).resolve()
    page = root / "START-HERE.html"
    if not page.is_file():
        raise ValueError("보고서 HTML이 없습니다.")
    raw = page.read_text(encoding="utf-8")
    if "\ufffd" in raw:
        raise ValueError("보고서 내 깨진 UTF-8 대체문자가 존재합니다.")
    scanner = _ReportParser()
    scanner.feed(raw)
    scanner.close()
    if scanner.scripts or scanner.open_details:
        raise ValueError("실행 스크립트 또는 닫히지 않은 details가 있습니다.")
    if not scanner.styles or "max-height:760px" in "".join(scanner.styles):
        raise ValueError("사용자 도면이 잘릴 수 있는 이전 크기 제한이 남아 있습니다.")
    if len(set(scanner.ids)) != len(scanner.ids):
        raise ValueError("중복된 HTML 섹션 ID")
    mandatory = {"overview", "diagram", "decision", "ops", "cost", "evidence", "next"}
    if not mandatory.issubset(set(scanner.ids)):
        raise ValueError("사용자 보고서 핵심 영역 누락")
    if scanner.details != scanner.summaries or scanner.details < 1:
        raise ValueError("고급 상세는 summary가 있는 details로 제공해야 합니다.")
    if raw.find("id='overview'") > raw.find("id='diagram'"):
        raise ValueError("권장 결과 요약이 AWS 설계도보다 뒤에 있습니다.")
    checked = []
    for href in scanner.hrefs:
        file, fragment = _safe_local_path(root, href)
        if fragment and file is None and fragment not in scanner.ids:
            raise ValueError("이동할 수 없는 HTML 내부 앵커: " + href)
        checked.append(href)
    if not scanner.images:
        raise ValueError("AWS 참조 도면 이미지가 없습니다.")
    embedded_svgs = 0
    for src, alt in scanner.images:
        if not alt or not alt.strip():
            raise ValueError("이미지의 대체 텍스트가 빠졌습니다.")
        prefix = "data:image/svg+xml;base64,"
        if not src or not src.startswith(prefix):
            raise ValueError("HTML 이미지는 오프라인 내장 SVG만 허용합니다.")
        try:
            image = base64.b64decode(src[len(prefix):], validate=True)
            parsed = ElementTree.fromstring(image)
        except (ValueError, ElementTree.ParseError) as exc:
            raise ValueError("HTML 내장 SVG가 유효하지 않습니다.") from exc
        if not parsed.tag.endswith("svg"):
            raise ValueError("HTML 내장 이미지가 SVG가 아닙니다.")
        embedded_svgs += 1
    if "AWS To-Be" not in raw or "미검증" not in raw and "검증" not in raw:
        raise ValueError("AWS To-Be/실환경 검증 전 경고가 보이지 않습니다.")
    manifest = json.loads((root / "artifact-index.json").read_text(encoding="utf-8"))
    for item in manifest["primary_files"] + manifest.get("supplementary_files", []):
        file, _ = _safe_local_path(root, item["path"])
        if hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("산출물 SHA-256 불일치: " + item["path"])
    for file_name in ("aws-topology.svg", "application-graph.svg",
                      "deliverables/01-aws-to-be.svg"):
        _svg(root / file_name)
    png = (root / "deliverables/01-aws-to-be.png").read_bytes()
    if not png.startswith(PNG_HEADER) or len(png) < 24:
        raise ValueError("AWS PNG 헤더 손상")
    width, height = struct.unpack(">II", png[16:24])
    if not (100 <= width <= 32000 and 100 <= height <= 32000):
        raise ValueError("AWS PNG 해상도가 비정상입니다.")
    topology = json.loads((root / "aws-topology.json").read_text(encoding="utf-8"))
    nodes = {n["id"] for n in topology["nodes"]}
    if len(nodes) != len(topology["nodes"]) or any(
        e["source"] not in nodes or e["target"] not in nodes
        for e in topology["edges"]
    ):
        raise ValueError("AWS 토폴로지의 중복 노드 또는 연결 대상 누락")
    if (topology["counts"].get("nodes") != len(nodes) or
            topology["counts"].get("edges") != len(topology["edges"])):
        raise ValueError("AWS 토폴로지 노드·연결 수 일관성 위반")
    mode = manifest["analysis_goal"]
    if mode == "migrate_onprem":
        if manifest["onprem_inventory_analyzed"]:
            if raw.find("id='onprem-as-is'") < 0:
                raise ValueError("온프레미스 사용자 입력 As-Is 영역 누락")
            _svg(root / "as-is-topology.svg")
        elif "id='migration-warning'" not in raw:
            raise ValueError("온프레미스 Inventory 부재 안내 누락")
        if manifest["migration_review_generated"] and "id='migration-assessment'" not in raw:
            raise ValueError("마이그레이션 후보 비교 누락")
    elif mode == "new_aws":
        if "id='onprem-as-is'" in raw or "id='migration-assessment'" in raw:
            raise ValueError("신규 AWS 모드에 이전 전용 화면이 표시됩니다.")
    else:
        raise ValueError("알 수 없는 분석 모드")
    if not manifest["production_ready"] and "승인 전" not in raw:
        raise ValueError("AWS 생산 환경 미검증 상태 표시 누락")
    # Detailed user-facing report and ground-truth links remain separate.
    if not "비용" in raw or "AWS 계정" not in raw:
        raise ValueError("비용/계정 미검증 상태가 빠졌습니다.")
    return {
        "schema_version": "1.0",
        "status": "automated_structural_checks_passed",
        "analysis_goal": mode,
        "checks": {
            "utf8_text": True, "html_semantics_and_link_targets": True,
            "self_contained_svg": True, "diagram_viewports": True,
            "png_dimensions": True, "artifact_hashes": True,
            "topology_node_and_edge_refs": True,
            "as_is_to_be_status": True,
        },
        "linked_artifacts_checked": len(checked),
        "embedded_svg_count": embedded_svgs,
        "primary_assets_checked": len(manifest["primary_files"]),
        "supplementary_assets_checked": len(manifest.get("supplementary_files", [])),
        "browser_rendered": False,
        "mobile_viewport_checked": False,
        "manual_visual_review_completed": False,
        "real_repository_accuracy_audited": False,
        "aws_account_checked": False,
        "note": "구조/경로/상태 자동 검증만 통과했습니다. 실제 데스크톱·모바일 브라우저 시각·글꼴·아이콘과 외부 공개 프로젝트 정확성 감사는 별도입니다.",
    }


def write_report_quality(folder):
    report = audit_report(folder)
    output = Path(folder) / "report-qa.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return report
