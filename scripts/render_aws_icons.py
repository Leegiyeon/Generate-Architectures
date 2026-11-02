"""Render icon-based AWS reference architectures with the Diagrams library.

Uses bundled AWS service icons, no remote requests or arbitrary icon paths.
"""
import base64
from pathlib import Path
import xml.etree.ElementTree as ET

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import Fargate, Lambda
from diagrams.aws.database import Dynamodb, RDS
from diagrams.aws.management import Cloudwatch
from diagrams.aws.network import ALB, APIGateway, CloudFront, Route53
from diagrams.aws.security import Cognito, WAF
from diagrams.aws.storage import S3
from diagrams.onprem.client import Client, User
from diagrams.aws.general import MobileClient

AWS_ICONS = {
    "Route 53": Route53,
    "CloudFront": CloudFront,
    "API Gateway": APIGateway,
    "Application Load Balancer": ALB,
    "Lambda": Lambda,
    "ECS Fargate": Fargate,
    "DynamoDB": Dynamodb,
    "Amazon RDS": RDS,
    "S3": S3,
    "AWS WAF": WAF,
    "Amazon Cognito": Cognito,
    "CloudWatch": Cloudwatch,
}
CLIENT_ICONS = {"User": User, "Client": Client, "Mobile App": MobileClient}
GROUPS = (
    ("01  Entry / Delivery", ("Route 53", "CloudFront", "API Gateway", "Application Load Balancer")),
    ("02  Compute / API", ("Lambda", "ECS Fargate")),
    ("03  Data", ("DynamoDB", "Amazon RDS", "S3")),
    ("04  Security", ("AWS WAF", "Amazon Cognito")),
    ("05  Observability", ("CloudWatch",)),
)
DISPLAY_NAMES = {
    "Route 53": "Amazon\nRoute 53",
    "CloudFront": "Amazon\nCloudFront",
    "API Gateway": "Amazon API\nGateway",
    "Application Load Balancer": "Application\nLoad Balancer",
    "Lambda": "AWS\nLambda",
    "ECS Fargate": "AWS Fargate\n(ECS)",
    "DynamoDB": "Amazon\nDynamoDB",
    "Amazon RDS": "Amazon\nRDS",
    "S3": "Amazon S3",
    "AWS WAF": "AWS WAF",
    "Amazon Cognito": "Amazon\nCognito",
    "CloudWatch": "Amazon\nCloudWatch",
    "Mobile App": "Mobile\nclient",
}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def embed_icons(svg_file):
    """Make SVG independently viewable outside the Actions runner.

    Graphviz usually emits local filesystem hrefs for Diagrams icon PNGs.
    Replace those refs with embedded PNG data URIs before exporting.
    """
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    tree = ET.parse(svg_file)
    images = 0
    for element in tree.iter("{" + SVG_NS + "}image"):
        attr = "{" + XLINK_NS + "}href"
        href = element.get(attr) or element.get("href")
        if not href or href.startswith("data:"):
            continue
        icon = Path(href)
        if not icon.is_file() or icon.suffix.lower() != ".png":
            raise ValueError("Diagrams generated an unavailable or unsupported icon")
        element.set(attr, "data:image/png;base64," + base64.b64encode(icon.read_bytes()).decode("ascii"))
        images += 1
    if not images:
        raise ValueError("Icon render failed: no AWS or client icons found in SVG")
    tree.write(svg_file, encoding="utf-8", xml_declaration=True)
    return images


def render_icon_diagram(architecture, output_dir):
    """Draw only explicitly-supported nodes and relationships from a validated reference design."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    identifiers = architecture["nodes"]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate service identifier in architecture")
    unknown = set(identifiers) - set(AWS_ICONS) - set(CLIENT_ICONS)
    if unknown:
        raise ValueError("Unsupported service nodes: " + ", ".join(sorted(unknown)))
    for source, target in architecture["edges"]:
        if source not in identifiers or target not in identifiers:
            raise ValueError("Architecture edge refers to an unknown node")
    title = architecture["pattern"] + "  |  AWS reference design (not deployed)"
    graph_attrs = {
        "bgcolor": "white",
        "pad": "0.50",
        "nodesep": "0.55",
        "ranksep": "1.0",
        "splines": "spline",
        "fontname": "Noto Sans CJK KR",
        "fontsize": "17",
        "fontcolor": "#18263A",
    }
    node_attrs = {"fontname": "Noto Sans CJK KR", "fontsize": "11", "fontcolor": "#243348"}
    edge_attrs = {"color": "#64748B", "penwidth": "1.6", "arrowsize": "0.8"}
    cluster_attrs = {
        "bgcolor": "#F8FAFC",
        "color": "#CBD5E1",
        "fontname": "Noto Sans CJK KR",
        "fontcolor": "#475569",
        "fontsize": "13",
        "style": "rounded",
        "margin": "18",
    }

    output_prefix = str(output_dir / "architecture")
    with Diagram(
        title, filename=output_prefix, show=False, direction="LR",
        outformat=["png", "svg", "dot"],
        graph_attr=graph_attrs, node_attr=node_attrs, edge_attr=edge_attrs,
    ):
        nodes = {}
        for name in identifiers:
            if name in CLIENT_ICONS:
                nodes[name] = CLIENT_ICONS[name](DISPLAY_NAMES.get(name, name))
        with Cluster("AWS Cloud  /  proposed", graph_attr={
            **cluster_attrs, "bgcolor": "#FFFFFF", "color": "#94A3B8",
            "fontsize": "16", "margin": "24"
        }):
            for group_title, services in GROUPS:
                present = [name for name in services if name in identifiers]
                if not present:
                    continue
                with Cluster(group_title, graph_attr=cluster_attrs):
                    for name in present:
                        nodes[name] = AWS_ICONS[name](DISPLAY_NAMES.get(name, name))

        for source, target in architecture["edges"]:
            if source in ("AWS WAF", "Amazon Cognito"):
                edge = Edge(color="#C77D19", style="dashed", penwidth="1.35",
                            constraint="false", label="protects" if source == "AWS WAF" else "sign-in")
            elif target == "CloudWatch":
                edge = Edge(color="#64748B", style="dotted", penwidth="1.3",
                            constraint="false", label="telemetry")
            else:
                edge = Edge(color="#2563A6", penwidth="1.9")
            nodes[source] >> edge >> nodes[target]

    paths = {ext: output_dir / ("architecture." + ext) for ext in ("png", "svg", "dot")}
    for path in paths.values():
        if not path.is_file() or path.stat().st_size < 100:
            raise RuntimeError("Expected diagram artifact missing or empty: " + str(path))
    count = embed_icons(paths["svg"])
    if count < len(identifiers):
        raise RuntimeError("Not all service icons appeared in SVG output")
    return paths
