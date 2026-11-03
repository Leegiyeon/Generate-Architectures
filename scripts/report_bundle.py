"""한국어 사용자용 AWS 아키텍처 결과물: 실행되지 않는 오프라인 HTML/4개 주요 파일.

AWS 계정/배포를 실행하지 않고 기생성된 검증 전 제안·정적 증거만 읽습니다.
CSP로 스크립트, 외부 CSS/이미지 호출을 차단하고 문자열을 HTML 이스케이프합니다.
"""
import base64
import hashlib
from html import escape
import json
from pathlib import Path
import shutil

try:
    from .cost_scenarios import scenario_markdown
except ImportError:
    from cost_scenarios import scenario_markdown

FILES = (
    ("01-aws-to-be.svg", "AWS To-Be 상세 논리도", "diagram"),
    ("01-aws-to-be.png", "AWS To-Be 이미지", "diagram"),
    ("02-architecture-decisions.md", "서비스 선정·대안·ADR", "decision"),
    ("03-security-operations.md", "보안·확장성·운영", "operations"),
    ("04-cost-capacity.md", "비용·용량 및 미확인 항목", "cost"),
)
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'"

def safe(value):
    return escape(str(value), quote=True)

def markdown_value(value):
    return str(value).replace(chr(96), "'").replace("|", "/").replace("\n", " ").replace("\r", " ")

def cost_capacity_markdown(cost, operations, topology):
    demand=operations["scaling"]["demand"]
    rows=[
        "# 비용·용량 검토 — 사용자 입력 범위", "",
        "> AWS 전체 견적·청구서·리전별 서비스 가격 검증 결과가 아닙니다.",
        "", "- 비용 상태: " + cost["status"],
        "- 비용 시나리오 리전: " + (cost.get("region") or "미입력"),
        "- 제안 설계 리전: " + (topology.get("region") or "미확정"),
        "- 전체 인프라 비용: **미검증**",
        "- 단가 누락 항목: " + str(cost["unpriced_count"]), "",
        "## 1. 실제 입력된 비용 항목만 계산", "",
    ]
    if cost["complete"]:
        rows.append("- 월 입력 항목 합계: " + str(cost["monthly_total_usd"]) +
                    " USD (**입력 항목만**, 전체 AWS 청구액 아님)")
    elif cost.get("priced_subtotal_usd") is not None and cost["lines"]:
        rows.append("- 확인된 항목의 부분합: " + str(cost["priced_subtotal_usd"]) +
                    " USD (**미산정 항목 제외, 총액 아님**)")
    else:
        rows.append("- 비용: **미산정** (사용량·단가 근거 필요)")
    rows += ["", "| 항목 | 사용량 | 단가 상태 | 월간 금액 USD | 기준일 |",
             "| --- | --- | --- | ---: | --- |"]
    for item in cost["lines"]:
        rows.append("| " + markdown_value(item["id"]) + " | " +
                    markdown_value(item["quantity"])+" "+markdown_value(item["unit"]) +
                    " | "+markdown_value(item["status"])+" | "+
                    (markdown_value(item["monthly_amount_usd"]) if
                     item["monthly_amount_usd"] is not None else "미산정")+
                    " | "+(markdown_value(item.get("price_as_of")) if item.get("price_as_of")
                             else "미확정")+" |")
    if not cost["lines"]:
        rows.append("| 비용 시나리오 없음 | - | 미입력 | 미산정 | - |")
    rows += ["", "## 2. 용량·트래픽 사용자 입력", "",
             "| 입력 키 | 값 | 출처 |", "| --- | ---: | --- |"]
    for key in ("average_rps","peak_rps","peak_concurrent_connections",
                "latency_target_ms","availability_target_percent",
                "rto_minutes","rpo_minutes"):
        value=demand.get(key)
        rows.append("| "+key+" | "+(markdown_value(value) if value is not None else "미입력")+
                    " | "+demand["input_provenance"].get(key,"미확인")+" |")
    rows += ["", "## 3. 미산정 및 실제 검증 필요", "",
             "- 사용자의 실제 SKU/리전/전송량, NAT/ALB/RDS/CloudWatch/백업/보관·세금/할인 조건을 대조해야 합니다.",
             "- 평균/피크 RPS만으로 ECS Task 수·CPU·메모리·Lambda 동시성/계층 단가를 계산하지 않습니다.",
             "- 모든 Auto Scaling 임계값·최소/최대 용량·실측 쿼터는 실제 부하 테스트와 계정 확인 전까지 미확정입니다.",
             "- 비용 시나리오를 변경한 뒤 사용자가 수동 재분석할 수 있습니다.",
             "", cost["note"], ""]
    if "scenarios" in cost:
        rows += ["", scenario_markdown(cost)]
    return "\n".join(rows)

def generate_user_bundle(out, architecture, topology, graph, contract,
                         decision_matrix, adr, operations, cost, validation):
    """모든 기존 산출물이 생성된 후 실행하는 오프라인 읽기 전용 보고 단계."""
    out=Path(out)
    selected=next(c for c in decision_matrix["candidates"] if c["is_current_reference"])
    if (decision_matrix["selected_reference"] != adr["chosen_reference_detail"] or
        adr["gate"]["architecture"] != validation["decision_gate"] or
        topology["status"] != architecture["aws_topology"]["status"] or
        operations["selected_pattern"] != topology["pattern"]):
        raise ValueError("선택 결과·승인 상태·토폴로지·운영 보고서의 일관성 위반")
    if any(x["topology_node"] not in {n["id"] for n in topology["nodes"]}
           for x in operations["alerts"]):
        raise ValueError("운영 경보 대상이 현재 AWS 토폴로지에 없습니다.")
    if not cost["complete"] and cost["monthly_total_usd"] is not None:
        raise ValueError("누락된 비용 항목을 전체 금액으로 표시할 수 없습니다.")
    if adr["approval"]["approved"] or operations["production_ready"]:
        raise ValueError("자동 승인/실환경 검증 상태를 사용자 보고서에서 허용하지 않습니다.")
    destination=out/"deliverables"
    destination.mkdir(parents=True,exist_ok=True)
    for source,name in (("aws-topology.svg","01-aws-to-be.svg"),
                        ("aws-topology.png","01-aws-to-be.png"),
                        ("security-operations.md","03-security-operations.md")):
        shutil.copyfile(out/source,destination/name)
    decisions=(
        "# AWS 서비스 선정·제외 근거 — 사람 승인 전\n\n"
        "## 1. 실행 패턴과 대안\n\n" +
        (out/"architecture-decision-matrix.md").read_text(encoding="utf-8")+
        "\n## 2. DB 접근 패턴과 마이그레이션 위험\n\n"+
        (out/"data-access-decision.md").read_text(encoding="utf-8")+
        "\n## 3. ADR 및 최종 승인 기준\n\n"+
        (out/"decision-record.md").read_text(encoding="utf-8"))
    (destination/"02-architecture-decisions.md").write_text(decisions,encoding="utf-8")
    (destination/"04-cost-capacity.md").write_text(
        cost_capacity_markdown(cost,operations,topology),encoding="utf-8")
    blocked=(validation["decision_gate"]=="blocked" or
             topology["status"]=="blocked_for_review" or
             decision_matrix["status"]=="blocked_for_review")
    status=("조건 충돌 — 설계 수정 및 검토 필요" if blocked else
            "권장 참조 설계 — 승인 전 추가 검증 필요")
    question_list=[x["question"] for x in contract["unknowns"]]
    ops_questions=[x["question"] for x in operations["questions"]]
    selected_title=selected["title"]
    candidates=[c for c in decision_matrix["candidates"]
                if c["id"] in decision_matrix["alternative_candidates"]]
    cost_summary=("입력 항목 합계 "+str(cost["monthly_total_usd"])+" USD (전체 인프라 청구액 아님)"
                  if cost["complete"] else
                  "입력된 항목의 부분합 "+str(cost["priced_subtotal_usd"])+
                  " USD (미산정 항목 제외)" if cost["lines"] and
                  cost.get("priced_subtotal_usd") is not None else "미산정")
    manifest={
        "schema_version":"1.0", "state":"unapproved_reference_design",
        "status":status, "production_ready":False, "aws_account_checked":False,
        "chosen_option":architecture["option_id"],
        "decision_gate":validation["decision_gate"],
        "topology_status":topology["status"],
        "cost_status":cost["status"],
        "cost_total_only_covers_user_input":True,
        "reference_nodes":topology["counts"]["nodes"],
        "reference_edges":topology["counts"]["edges"],
        "observations":len(contract["observations"]),
        "configuration_indicators":len(contract["configuration_inferences"]),
        "explicit_requirements":len(contract["user_requirements"]),
        "requirements_unknown":len(question_list),
        "parser_partial":contract["status"]=="partial",
        "primary_files":[],
    }
    for name,description,kind in FILES:
        path=destination/name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("사용자 결과물 생성 실패: "+name)
        manifest["primary_files"].append({
            "path":"deliverables/"+name,"description":description,"kind":kind,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    (out/"artifact-index.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    md=[
        "# AWS 아키텍처 검토 — 시작하기", "",
        "> **실제 AWS 배포·계정 조회 미실행 / 사용자 승인 전 / 정적 참조 설계**", "",
        "- 상태: "+status,
        "- 현재 참조 패턴: "+markdown_value(architecture["pattern"]),
        "- 검토 차단: "+str(validation["counts"]["blocker"])+"건",
        "- 정적 관찰 근거: "+str(len(contract["observations"]))+"건",
        "- 설정 기반 추정 단서: "+str(len(contract["configuration_inferences"]))+"건",
        "- 사용자 명시 입력: "+str(len(contract["user_requirements"]))+"개",
        "- 확인 질문: "+str(len(question_list))+"개",
        "- 비용: "+cost_summary,"",
        "## 1. 주요 결과물 4가지", "",
        "| 순서 | 파일 | 목적 |", "| --- | --- | --- |",
        "| ① | [AWS To-Be SVG](deliverables/01-aws-to-be.svg) / [PNG](deliverables/01-aws-to-be.png) | 논리 VPC·AZ·서비스 제안 |",
        "| ② | [선정·대안·ADR](deliverables/02-architecture-decisions.md) | 서비스별 이유 및 제외 사유, 승인 대기 |",
        "| ③ | [보안·운영](deliverables/03-security-operations.md) | SG·IAM·스케일링·알람·백업 검토 |",
        "| ④ | [비용·용량](deliverables/04-cost-capacity.md) | 사용자 입력 기준 요금과 미확정 용량 |",
        "", "## 2. 추천안 선정 근거", ""
    ]
    md.extend("- "+markdown_value(x) for x in selected["rationale"])
    md+=["","## 3. 대안 검토", ""]
    md.extend("- "+markdown_value(x["title"])+": "+markdown_value(x["tradeoffs"][0])
              for x in candidates)
    md+=["","## 4. As-Is / To-Be / 실제 검증의 경계", "",
         "- **As-Is (정적 코드 관찰)**: [애플리케이션 그래프](application-graph.svg) / [근거 보고서](evidence-report.md). 코드 실행 및 데이터 흐름 실측은 아님.",
         "- **To-Be (AWS 제안)**: [설계도](deliverables/01-aws-to-be.svg). 실제 운영 계정의 자원이 아님.",
         "- **검증 전**: 서비스별 비용·IAM/SG·부하·복구/장애 시험·SLO 미검증.",
         "- **미실행**: AWS 자원 생성/변경/삭제·Terraform apply·계정 자격증명 입력을 수행하지 않음.",
         "", "## 5. 우선 확인할 질문", ""]
    md.extend("- "+markdown_value(x) for x in question_list[:8])
    md.extend("- "+markdown_value(x) for x in ops_questions[:4] if x not in question_list[:8])
    md+=["", "## 6. 수동 재분석", "",
         "1. 설계 차단/누락 조건을 확인하고 저장소의 .architecture/requirements.json에 비기밀 값을 추가합니다.",
         "2. GitHub → Actions → AWS 아키텍처 검토 자동화 → Run workflow를 수동 실행합니다.",
         "3. 다운로드한 Artifact에서 START-HERE.html을 우선 확인합니다.", "",
         "[전체 기술 보고서](recommendation.md) · [정적 검증](validation.md) · [결과물 해시](artifact-index.json)", "",
         "**주의:** 실제 운영 인프라의 보안/가용성/비용은 이 도구로 검증하지 않았습니다.",""]
    (out/"START-HERE.md").write_text("\n".join(md),encoding="utf-8")

    def li(values, limit=7):
        return "".join("<li>"+safe(v)+"</li>" for v in values[:limit]) or "<li>추가 항목 없음 (실환경 검증은 별도)</li>"
    def row(*cells):
        return "<tr>"+"".join("<td>"+safe(x)+"</td>" for x in cells)+"</tr>"
    alt_html="".join(row(x["title"],x["status"],
                          "; ".join(z["reason"] for z in x["blockers"][:2])
                          or x["tradeoffs"][0]) for x in candidates)
    if not alt_html:
        alt_html="<tr><td colspan='3'>검토 가능한 대안 없음</td></tr>"
    cost_html="".join(row(x["id"],x["quantity"]+" "+x["unit"],
                          x["status"],x["monthly_amount_usd"] if x["monthly_amount_usd"] is not None
                          else "미산정") for x in cost["lines"][:12])
    if not cost_html:
        cost_html="<tr><td colspan='4'>사용량·단가 입력이 없어 비용 미산정</td></tr>"
    css="""
:root{font-family:system-ui,-apple-system,Segoe UI,Apple SD Gothic Neo,Noto Sans CJK KR,sans-serif;background:#f3f6fa;color:#193451}
*{box-sizing:border-box}body{margin:0;line-height:1.6}a{color:#164f93}header{background:#112944;color:#fff;padding:32px max(22px,calc((100% - 1100px)/2))}
header h1{margin:6px 0;font-size:clamp(24px,3vw,35px)}header p{color:#dbe8f6}main{max-width:1100px;margin:auto;padding:16px}
nav{display:flex;flex-wrap:wrap;gap:9px;margin-top:17px}nav a{border:1px solid #7496b7;border-radius:23px;padding:6px 12px;color:white;text-decoration:none;font-size:13px}
.panel,.card{background:#fff;border:1px solid #dce5ee;border-radius:12px;padding:20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{margin:0}.card strong{display:block;font-size:13px;color:#2d587c}.card b{font-size:18px}
h2{font-size:21px;color:#163e64;margin-top:0}h3{font-size:16px}.pill{display:inline-block;border-radius:16px;background:#d8e9fe;color:#144575;padding:3px 10px}
.caution{padding:12px;border-left:4px solid #d19c2d;background:#fff6e1;border-radius:5px}
.diagram{display:block;width:100%;height:auto;max-height:760px;object-fit:contain}
.links{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}.links a{background:#e9f2fc;padding:7px 12px;border-radius:7px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #e0e7ef;vertical-align:top}th{background:#edf3f8}
li{margin:7px 0}.muted,small{color:#697d90}footer{text-align:center;padding:22px;color:#54708e}
@media(max-width:720px){.grid{grid-template-columns:1fr}.panel{padding:14px}header{padding:22px 15px}table{display:block;overflow-x:auto}}
"""
    image=base64.b64encode((out/"aws-topology.svg").read_bytes()).decode("ascii")
    if not image:
        raise ValueError("렌더링된 AWS 설계도가 비어 있습니다.")
    # 시나리오별 금액은 사용자 직접 입력한 수량에 한해서만 출력합니다.
    scenario_html = ""
    if "scenarios" in cost:
        comparison = []
        for key, label in (("minimum", "최소"), ("baseline", "기준"), ("peak", "피크")):
            value = cost["scenarios"][key]
            comparison.append(row(
                label,
                value["priced_subtotal_usd"] if value["priced_subtotal_usd"] is not None else "미산정",
                value["monthly_total_usd"] if value["monthly_total_usd"] is not None else "미산정",
                value["unpriced_count"],
            ))
        coverage = cost.get("topology_coverage", {})
        scenario_html = (
            "<h3>사용자 입력 최소·기준·피크 시나리오</h3>"
            "<table><thead><tr><th>시나리오</th><th>부분합 USD</th><th>입력 항목 합계 USD</th>"
            "<th>미산정 항목</th></tr></thead><tbody>" +
            "".join(comparison) + "</tbody></table>"
            "<p class='caution'>To-Be 비용 분류 누락: " +
            safe(", ".join(coverage.get("missing_categories", [])) or
                 "분류상 없음 (SKU·사용량 검증 전)") +
            ". 전체 AWS 청구액 검증이 아닙니다.</p>"
        )
    html_doc=(
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\""+safe(CSP)+"\">"
        "<title>AWS 아키텍처 설계 검토</title><style>"+css+"</style></head><body>"
        "<header><small>Generate-Architectures · Architecture Designer</small>"
        "<h1>AWS 아키텍처 설계 검토</h1>"
        "<p>저장소 정적 분석과 입력된 요구사항에 따른 <b>참조 설계 제안</b>입니다. AWS 계정·배포·보안 인증은 수행하지 않았습니다.</p>"
        "<span class='pill'>"+safe(status)+"</span><p>정적 분석 시각(UTC): "+
        safe(contract["analyzed_at_utc"])+"</p>"
        "<nav><a href='#overview'>요약</a><a href='#diagram'>① 설계도</a>"
        "<a href='#decision'>② 선정 근거</a><a href='#ops'>③ 보안·운영</a>"
        "<a href='#cost'>④ 비용·용량</a><a href='#evidence'>As-Is/To-Be</a>"
        "<a href='#next'>재분석</a></nav></header><main>"
        "<section id='overview' class='grid'>"
        "<div class='card'><strong>권장 참조안</strong><b>"+safe(architecture["pattern"])+
        "</b><br><small>사람 승인 전</small></div>"
        "<div class='card'><strong>검토 차단</strong><b>"+str(validation["counts"]["blocker"])+
        "건</b><br><small>추가 확인 질문 "+str(len(question_list))+"개</small></div>"
        "<div class='card'><strong>월간 비용 상태</strong><b>"+safe(cost["status"])+
        "</b><br><small>"+safe(cost_summary)+"</small></div></section>"
        "<section class='panel' id='diagram'><h2>① AWS To-Be 설계도</h2>"
        "<p class='muted'>논리 VPC/가용 영역·서비스 연결. 실제 클라우드 구성·주소·라우팅 검증 결과가 아닙니다.</p>"
        "<div class='links'><a href='deliverables/01-aws-to-be.svg'>SVG 확대</a>"
        "<a href='deliverables/01-aws-to-be.png'>PNG</a>"
        "<a href='aws-topology.json'>노드/연결 근거 JSON</a></div>"
        "<img class='diagram' alt='AWS To-Be 서비스와 네트워크 제안' src='data:image/svg+xml;base64,"+
        image+"'>"
        "<p class='caution'>"+safe(topology["status"])+" · 서비스/영역 "+str(topology["counts"]["nodes"])+
        "개 · 논리 연결 "+str(topology["counts"]["edges"])+"개. AWS 계정에서 확인하지 않았습니다.</p></section>"
        "<section class='panel' id='decision'><h2>② 서비스 선정 및 제외 근거</h2>"
        "<h3>"+safe(selected_title)+" (현재 참조 패턴)</h3>"
        "<ul>"+li(selected["rationale"])+"</ul>"
        "<h3>대안 비교</h3><table><thead><tr><th>후보</th><th>상태</th><th>제외/검토 이유</th>"
        "</tr></thead><tbody>"+alt_html+"</tbody></table>"
        "<div class='links'><a href='deliverables/02-architecture-decisions.md'>"
        "서비스 선정·DB 대안·ADR 전체</a></div></section>"
        "<section class='panel' id='ops'><h2>③ 보안·트래픽·운영</h2>"
        "<p>To-Be의 실제 제안된 서비스에 연결된 항목만 제공합니다. IAM/SG·Auto Scaling/CloudWatch/복구/롤백은 미검증입니다.</p>"
        "<div class='grid'><div class='card'><strong>운영/보안 통제</strong><b>"+
        str(len(operations["security_and_operations"]))+"개</b></div>"
        "<div class='card'><strong>확장 정책 후보</strong><b>"+
        str(len(operations["scaling"]["policies"]))+"개</b><br><small>임계값 미정</small></div>"
        "<div class='card'><strong>경보 후보</strong><b>"+
        str(len(operations["alerts"]))+"개</b><br><small>미생성</small></div></div>"
        "<h3>주요 통제</h3><ul>"+li([x["title"] for x in operations["security_and_operations"]],9)+
        "</ul><div class='links'><a href='deliverables/03-security-operations.md'>"
        "보안·운영 보고서</a><a href='network-policy.md'>네트워크 정책 제안</a></div></section>"
        "<section class='panel' id='cost'><h2>④ 비용·용량</h2>"
        "<p class='caution'>"+safe(cost_summary)+
        "<br>입력 SKU만 계산하며 실제 AWS 총액, 할인/세금/데이터 전송, RPS 처리량을 보장하지 않습니다.</p>"
        "<table><thead><tr><th>항목</th><th>사용량</th><th>가격 상태</th><th>금액 USD</th></tr>"
        "</thead><tbody>"+cost_html+"</tbody></table>"
        + scenario_html +
        "<p>입력 피크 RPS: <b>"+
        (safe(operations["scaling"]["demand"]["peak_rps"])
         if operations["scaling"]["demand"]["peak_rps"] is not None else "미입력")+
        "</b> · 타깃 임계값·최소/최대 용량: <b>미정(실측 필요)</b></p>"
        "<div class='links'><a href='deliverables/04-cost-capacity.md'>"
        "비용·용량 상세</a></div></section>"
        "<section class='panel' id='evidence'><h2>As-Is 사실 / To-Be 가정 / 미검증 항목</h2>"
        "<table><thead><tr><th>구분</th><th>내용</th></tr></thead><tbody>"+
        row("정적 코드 관찰", str(len(contract["observations"]))+"개, 실제 실행 확인 아님")+
        row("설정/의존성 단서",str(len(contract["configuration_inferences"]))+"개, 기능·런타임 추정")+
        row("사용자 명시 조건",str(len(contract["user_requirements"]))+"개, 기본값은 사용자 승인 아님")+
        row("AWS To-Be",topology["status"]+", AWS 계정에서 실측하지 않은 제안")+
        row("검증 미실행","실제 IAM·SG·성능·복구·인프라 비용·AWS 배포")+
        "</tbody></table><div class='links'>"
        "<a href='application-graph.svg'>As-Is 코드 구조</a>"
        "<a href='evidence-report.md'>근거·미확인 조건</a>"
        "<a href='validation.md'>정적 제약 보고서</a></div>"+
        ("<p class='caution'>코드 파싱 일부 실패: 미관측을 부재로 해석할 수 없습니다.</p>"
         if contract["status"]=="partial" else "")+"</section>"
        "<section class='panel' id='next'><h2>우선 확인 사항 및 재분석</h2>"
        "<h3>추가 요구사항</h3><ul>"+li(question_list,8)+"</ul>"
        "<h3>운영 검증 질문</h3><ul>"+li(ops_questions,5)+"</ul>"
        "<h3>수동 재분석</h3><ol>"
        "<li>저장소의 .architecture/requirements.json에 비기밀 업무 요구와 운영 조건을 보완합니다.</li>"
        "<li>GitHub → Actions → AWS 아키텍처 검토 자동화 → <b>Run workflow</b>를 실행합니다.</li>"
        "<li>Artifacts에서 aws-architecture-recommendation을 다운로드하고 이 보고서를 확인합니다.</li>"
        "</ol><div class='links'><a href='START-HERE.md'>한국어 요약</a>"
        "<a href='recommendation.md'>개발자 상세 보고서</a>"
        "<a href='artifact-index.json'>산출물·해시</a></div></section>"
        "</main><footer>Generate-Architectures · 실제 AWS 계정 조회/수정 및 자동 배포 없음</footer>"
        "</body></html>"
    )
    if "<script" in html_doc.lower() or "http://" in html_doc.lower():
        raise ValueError("사용자용 HTML에 실행 스크립트·외부 자원 링크를 포함할 수 없습니다.")
    (out/"START-HERE.html").write_text(html_doc,encoding="utf-8")
    return {
        "entrypoint":"START-HERE.html", "markdown":"START-HERE.md",
        "manifest":"artifact-index.json",
        "primary_files":[x["path"] for x in manifest["primary_files"]],
        "status":"review_required_not_deployed","production_ready":False,
    }
