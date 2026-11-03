"""AWS To-Be 상세 토폴로지의 영역 계층과 트래픽 흐름을 Graphviz로 렌더링.

현재 서비스 아이콘 아키텍처와 별도로 VPC/Subnet/AZ 경계를 표시합니다.
모든 요소는 설계 후보이며 배포 확인 상태가 아닙니다.
"""
import html
import json
from pathlib import Path
import subprocess
import diagrams
from diagrams.aws.compute import EC2

try:
    from .render_aws_icons import AWS_ICONS, CLIENT_ICONS, embed_icons
except ImportError:
    from render_aws_icons import AWS_ICONS, CLIENT_ICONS, embed_icons

# 신뢰한 Diagrams 패키지의 번들 아이콘만 사용. 원격 아이콘과 임의 이미지 경로는 사용하지 않음.
SERVICE_ICONS = {
    "client": CLIENT_ICONS["User"], "observability": AWS_ICONS["CloudWatch"],
    "cdn": AWS_ICONS["CloudFront"], "bucket": AWS_ICONS["S3"],
    "waf": AWS_ICONS["AWS WAF"], "api": AWS_ICONS["API Gateway"],
    "lambda": AWS_ICONS["Lambda"], "dynamodb": AWS_ICONS["DynamoDB"],
    "cognito": AWS_ICONS["Amazon Cognito"],
    "alb": AWS_ICONS["Application Load Balancer"],
    "rds": AWS_ICONS["Amazon RDS"], "rds_standby": AWS_ICONS["Amazon RDS"],
    "ec2_a": EC2, "ec2_b": EC2,
}

def _icon_for(identifier):
    component = SERVICE_ICONS.get(identifier)
    if identifier.startswith("task_"):
        component = AWS_ICONS["ECS Fargate"]
    if component is None:
        return None
    root = Path(diagrams.__file__).resolve().parent.parent
    icon = (root / component._icon_dir / component._icon).resolve()
    if not icon.is_file() or icon.suffix.lower() != ".png" or not icon.is_relative_to(root):
        raise ValueError("번들 AWS 아이콘 경로를 확인할 수 없습니다.")
    return icon

BOUNDARY_KINDS = {
    "boundary", "vpc", "az", "subnet_public", "subnet_private",
    "subnet_database",
}
COLORS = {
    "boundary": ("#F8FAFC", "#94A3B8"),
    "vpc": ("#F0FDF4", "#15803D"),
    "az": ("#FAF5FF", "#7E22CE"),
    "subnet_public": ("#E0F2FE", "#0369A1"),
    "subnet_private": ("#F0FDF4", "#15803D"),
    "subnet_database": ("#FEF3C7", "#B45309"),
    "client": ("#E2E8F0", "#475569"),
    "network": ("#DBEAFE", "#2563EB"),
    "compute": ("#F5F3FF", "#7C3AED"),
    "database": ("#FFEDD5", "#EA580C"),
    "database_group": ("#FFEDD5", "#EA580C"),
    "storage": ("#FDE68A", "#D97706"),
    "security": ("#FCE7F3", "#BE185D"),
    "management": ("#E2E8F0", "#475569"),
}
EDGE_STYLE = {
    "traffic": ("#1D4ED8", "solid", "normal"),
    "placement": ("#94A3B8", "dotted", "none"),
    "trust_boundary": ("#D97706", "dashed", "normal"),
    "policy": ("#BE185D", "dashed", "normal"),
    "telemetry": ("#64748B", "dotted", "normal"),
    "replication": ("#7C3AED", "bold", "normal"),
    "authentication": ("#BE185D", "dashed", "normal"),
    "routing_proposal": ("#B45309", "dashed", "normal"),
    "dependency": ("#64748B", "dotted", "normal"),
}


def render_aws_topology(topology, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    indexed = {x["id"]: x for x in topology["nodes"]}
    if len(indexed) != len(topology["nodes"]):
        raise ValueError("토폴로지 노드 ID가 중복되었습니다.")
    children = {}
    for item in topology["nodes"]:
        parent = item["parent"]
        if parent is not None and parent not in indexed:
            raise ValueError("부모 영역 노드가 존재하지 않습니다.")
        children.setdefault(parent, []).append(item)
    lines = [
        "digraph AwsTopology {",
        'graph [rankdir=LR,bgcolor="white",pad="0.35",nodesep="0.30",ranksep="0.80",',
        'fontname="Noto Sans CJK KR",fontsize=16,labelloc=t,',
        'label="AWS To-Be 상세 토폴로지 · 설계 후보 / 실제 배포 아님"];',
        'node [fontname="Noto Sans CJK KR",fontsize=12,style="rounded,filled",penwidth=1.15];',
        'edge [fontname="Noto Sans CJK KR",fontsize=10,arrowsize=0.60,penwidth=1.15];',
    ]
    # 고정된 식별자만 Graphviz internal id로 사용. 사용자 입력은 JSON 문자열로 이스케이프.
    names = {item["id"]: "node_" + str(i) for i, item in enumerate(topology["nodes"])}

    def node(item):
        fill, border = COLORS.get(item["kind"], ("#E2E8F0", "#475569"))
        short = item["name"]
        if len(short) > 62:
            short = short[:59] + "..."
        icon = _icon_for(item["id"])
        if icon and item["id"] == "client":
            # 별도 행으로 라벨을 배치해 사용자 아이콘의 하단 선과 겹치지 않게 합니다.
            lines.append(names[item["id"]] + ' [shape=plain,style="",label=<'
                         '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">'
                         '<TR><TD WIDTH="112" HEIGHT="112" FIXEDSIZE="TRUE">'
                         '<IMG SRC="' + html.escape(str(icon), quote=True) + '" SCALE="TRUE"/>'
                         '</TD></TR><TR><TD>' + html.escape(short) + '</TD></TR></TABLE>>];')
        elif icon:
            # Graphviz image에는 설치된 Diagrams 번들 PNG만 제공.
            # SVG 반환 전에 로컬 PNG 참조를 Base64로 치환해 단독 열람 가능하게 합니다.
            lines.append(names[item["id"]] + " [label=" + json.dumps(short, ensure_ascii=False) +
                         ",shape=none,labelloc=b,imagescale=true,width=1.9,height=1.55,image=" +
                         json.dumps(str(icon), ensure_ascii=False) + "];")
        else:
            lines.append(names[item["id"]] + " [label=" + json.dumps(short, ensure_ascii=False) +
                         ',shape=box,fillcolor="' + fill + '",color="' + border + '"];')

    def walk(parent):
        for item in children.get(parent, []):
            if item["kind"] in BOUNDARY_KINDS:
                fill, border = COLORS[item["kind"]]
                lines.append("subgraph cluster_" + names[item["id"]] + " {")
                lines.append("label=" + json.dumps(item["name"], ensure_ascii=False) +
                             ';style="rounded";color="' + border +
                             '";bgcolor="' + fill +
                             '";fontname="Noto Sans CJK KR";fontsize=11;')
                # 클러스터(영역)와의 관계를 표시할 연결용 포인트. 실제 서비스가 아님.
                lines.append("anchor_" + names[item["id"]] +
                             ' [label="",shape=point,style=invis,width=0.01,height=0.01];')
                walk(item["id"])
                if not children.get(item["id"]):
                    # 빈 Public Subnet도 논리적 배치 영역으로 표시해야 합니다.
                    lines.append("empty_" + names[item["id"]] +
                                 ' [label="배치 범위 (논리)",shape=plaintext,fontsize=9];')
                lines.append("}")
            else:
                node(item)
                walk(item["id"])
    walk(None)

    for edge in topology["edges"]:
        if edge["source"] not in indexed or edge["target"] not in indexed:
            raise ValueError("토폴로지 간선의 서비스 ID를 찾지 못했습니다.")
        # 영역(클러스터)은 실제 서비스가 아니므로 내부 앵커에 연결합니다.
        def endpoint(ident):
            return ("anchor_" if indexed[ident]["kind"] in BOUNDARY_KINDS else "") + names[ident]
        color, style, arrow = EDGE_STYLE.get(edge["kind"], ("#64748B","solid","normal"))
        note = edge["purpose"]
        if len(note) > 26:
            note = note[:23] + "..."
        lines.append(endpoint(edge["source"]) + " -> " + endpoint(edge["target"]) +
                     ' [color="' + color + '",style="' + style + '",arrowhead="' +
                     arrow + '",label=' + json.dumps(note, ensure_ascii=False) + "];")
    lines.append("}")
    dot = output / "aws-topology.dot"
    dot.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for fmt in ("svg", "png"):
        subprocess.run(["dot", "-T" + fmt, str(dot),
                        "-o", str(output / ("aws-topology." + fmt))],
                       check=True, timeout=45, capture_output=True)
    # 모든 AWS 서비스 이미지가 SVG에서 로컬 파일에 의존하지 않도록 내장합니다.
    icons = embed_icons(output / "aws-topology.svg")
    if icons < sum(_icon_for(x["id"]) is not None for x in topology["nodes"]):
        raise RuntimeError("일부 AWS 서비스 아이콘을 렌더링하지 못했습니다.")
    return {"svg": output/"aws-topology.svg",
            "png": output/"aws-topology.png", "dot": dot,
            "embedded_icons": icons}
