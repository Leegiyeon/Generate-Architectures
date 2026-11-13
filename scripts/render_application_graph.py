"""애플리케이션 AST 그래프를 클러스터별 DOT/SVG/PNG로 내보냅니다.

이 다이어그램은 코드에서 확인된 구조이며, 별도의 AWS 서비스 추천도와 혼동하지 않습니다.
"""
import json
from pathlib import Path
import subprocess
from collections import defaultdict

GROUPS = (
    ("route", "API / 코드 선언 경로", "#E3F2FD", "#2563EB", "oval"),
    ("function", "함수 / 서비스", "#E8F5E9", "#2E7D32", "box"),
    ("model", "데이터 모델 정의", "#FFF3E0", "#EF6C00", "cylinder"),
    ("module", "모듈 / 파일", "#F4F4F5", "#6B7280", "folder"),
)
EDGE_STYLE = {
    "calls": ("#1565C0", "solid"),
    "handles": ("#2E7D32", "bold"),
    "imports": ("#64748B", "dashed"),
    "defines": ("#CBD5E1", "dotted"),
}


def render_application_diagram(graph, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # 사람이 검토할 수 있는 분량만 시각화. 전체 근거 그래프는 JSON을 참조합니다.
    by_type=defaultdict(list)
    for node in graph["nodes"]:
        by_type[node["type"]].append(node)
    selected=[]
    for kind,max_count in (("route",40),("function",90),("model",35),("module",45)):
        selected += by_type[kind][:max_count]
    selected=selected[:210]
    ids={n["id"]:"n"+str(i) for i,n in enumerate(selected)}
    raw=[
        "digraph Application {",
        'graph [rankdir=LR,bgcolor="white",pad="0.4",nodesep="0.3",ranksep="0.7",fontname="Noto Sans CJK KR",fontsize=16,labelloc=t,label="코드 근거 기반 애플리케이션 구성 (정적 분석 / 실행 검증 없음)"];',
        'node [fontname="Noto Sans CJK KR",fontsize=10,style="rounded,filled",penwidth=1.3];',
        'edge [fontname="Noto Sans CJK KR",arrowsize=0.6,penwidth=1.1];',
    ]
    for kind,label,fill,border,shape in GROUPS:
        these=[n for n in selected if n["type"]==kind]
        if not these: continue
        raw.append("subgraph cluster_"+kind+" {")
        raw.append('style="rounded"; color="'+border+'"; fontcolor="'+border+'"; fontsize=12;label='+json.dumps(label,ensure_ascii=False)+";")
        for n in these:
            displayed=n["name"]
            if len(displayed)>68:
                displayed=displayed[:65]+"..."
            if n.get("route_scope") == "router_local":
                displayed += "\n(라우터 내부 · 앱 등록 경로 미확인)"
            elif n.get("model_kind") == "sqlmodel_table":
                displayed += "\n(SQLModel 테이블 선언)"
            title=displayed+"\n"+n["path"]+":"+str(n["line"])
            raw.append(ids[n["id"]]+" [label="+json.dumps(title,ensure_ascii=False)+
                       ',shape='+shape+',fillcolor="'+fill+'",color="'+border+'"];')
        raw.append("}")
    if not ids:
        raw.append('empty [label="분석 가능한 함수/API/모델이 없습니다",shape=box,color="#CBD5E1"];')
    edges=0
    for edge in graph["edges"]:
        if edge["source"] not in ids or edge["target"] not in ids:
            continue
        color,style=EDGE_STYLE.get(edge["type"],("#64748B","solid"))
        raw.append(ids[edge["source"]]+" -> "+ids[edge["target"]]+
                   ' [color="'+color+'",style="'+style+'",label='+json.dumps(edge["type"])+"];")
        edges+=1
        if edges>=350:break
    raw.append("}")
    dot=output/"application-graph.dot"
    dot.write_text("\n".join(raw)+"\n",encoding="utf-8")
    for fmt in ("svg","png"):
        subprocess.run(["dot","-T"+fmt,str(dot),"-o",str(output/("application-graph."+fmt))],
                       check=True,timeout=45,capture_output=True)
    return {"visualized_nodes":len(ids),"visualized_edges":edges,
            "visualization_truncated":len(ids)<len(graph["nodes"]) or edges<len(graph["edges"])}
