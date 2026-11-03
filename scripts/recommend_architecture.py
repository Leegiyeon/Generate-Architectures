"""Generate Architectures: 저장소 분석 → 요구사항 검토 → 설계 대안 → 아이콘 다이어그램."""
import argparse
import json
import os
from pathlib import Path

if __package__:
    from .repository_analyzer import inspect_repository
    from .requirements_model import parse_requirements
    from .architecture_advisor import decide, markdown_report
    from .application_graph import build_application_graph
    from .render_application_graph import render_application_diagram
    from .ai_architecture_agent import review_architecture, markdown_ai_review
    from .cost_estimator import read_cost_inputs, estimate_costs, markdown_cost
    from .iac_policy_validator import read_terraform_plan, inspect_terraform_plan, markdown_iac
    from .architecture_validator import validate_architecture, markdown_validation, markdown_adr
    from .evidence_contract import build_evidence_contract, markdown_evidence
    from .aws_topology import design_aws_topology, markdown_topology
    from .render_aws_topology import render_aws_topology
    from .topology_network_policy import markdown_network_policy
    from .architecture_decision_engine import compare_architectures, markdown_decision_matrix
else:
    from repository_analyzer import inspect_repository
    from requirements_model import parse_requirements
    from architecture_advisor import decide, markdown_report
    from application_graph import build_application_graph
    from render_application_graph import render_application_diagram
    from ai_architecture_agent import review_architecture, markdown_ai_review
    from cost_estimator import read_cost_inputs, estimate_costs, markdown_cost
    from iac_policy_validator import read_terraform_plan, inspect_terraform_plan, markdown_iac
    from architecture_validator import validate_architecture, markdown_validation, markdown_adr
    from evidence_contract import build_evidence_contract, markdown_evidence
    from aws_topology import design_aws_topology, markdown_topology
    from render_aws_topology import render_aws_topology
    from topology_network_policy import markdown_network_policy
    from architecture_decision_engine import compare_architectures, markdown_decision_matrix


def scan(root):
    """기존 호출자 호환: 파일별 기술 근거를 반환합니다."""
    return inspect_repository(root)["manifests"]


def design(found, kind, budget):
    """기존 테스트/호출자 호환: 파일 목록만으로는 정적 Next.js를 확정하지 않습니다."""
    categories = {entry["category"] for entry in found}
    techs = sorted({entry["technology"] for entry in found})
    signals = {
        "api_routes": False, "nextjs": "Next.js" in techs,
        "next_static_export": False,
        "relational_database": False,
        "authentication_library": False,
        "background_job_library": False,
        "docker": "containers" in categories,
        "serverless_config": "serverless" in categories,
        "mobile": "mobile" in categories,
    }
    profile = {
        "schema_version": "1.0", "inspected_files": len(found),
        "scan_truncated": False, "technologies": techs,
        "manifests": found, "signals": signals,
        "evidence": {}, "static_candidate": "Vite" in techs and "backend" not in categories,
        "questions": [], "limitations": ["기술 설정 파일 목록만 제공되어 상세 분석은 수행하지 않았습니다."],
    }
    requirements = {"workload": kind, "deployment_preference": "auto",
                    "data_classification": "unknown", "environment": "dev"}
    if budget is not None:
        requirements["monthly_budget_usd"] = budget
    return decide(profile, requirements)


def run(repo, output, workload="auto", budget=None, requirements_file=None,
        ai_enabled=False, ai_model="gpt-6-luna", cost_input=None,
        live_pricing=False, terraform_plan=None):
    """구현 범위: 읽기 전용 정적 분석 및 검토용 AWS 참조 설계 생성."""
    root = Path(repo).resolve()
    if not root.is_dir():
        raise ValueError("분석 대상 저장소가 존재하지 않습니다.")
    requirements, explicit_fields = parse_requirements(
        requirements_file, root, budget, workload, return_provenance=True)

    profile = inspect_repository(root)
    # 실행 없이 구문만 파싱: 함수·API·모델의 근거 있는 구조 관계를 별도 그래프로 관리.
    graph = build_application_graph(root)
    actual_routes = [n for n in graph["nodes"] if n["type"] == "route"]
    if actual_routes:
        profile["signals"]["api_routes"] = True
        profile["static_candidate"] = False
        profile["evidence"]["ast_api_routes"] = [
            {"path": n["path"], "line": n["line"], "route": n["name"]}
            for n in actual_routes[:20]
        ]
    result = decide(profile, requirements)
    # 사실 / 사용자 명시입력 / 시스템 기본값 / 가정 / 미확인을 분리합니다.
    contract = build_evidence_contract(profile, graph, requirements, explicit_fields, result)
    result["questions"] = list(contract["questions"])
    if requirements.get("environment") == "production":
        result["questions"].append(
            "상용 운영 시 보안 검토·부하 테스트·장애 복구 훈련 책임자는 누구인가요?")
    result["evidence_contract"] = {
        "file": "evidence-contract.json",
        "observations": len(contract["observations"]),
        "inferences": len(contract["configuration_inferences"]),
        "explicit_requirements": len(contract["user_requirements"]),
        "questions": len(contract["questions"]),
        "partial": contract["status"] == "partial",
    }
    # VPC/Subnet/AZ/서비스 연결은 실제 배포가 아닌 '설계 후보'로 별도 토폴로지에 생성.
    topology = design_aws_topology(result, profile, requirements, contract)
    result["aws_topology"] = {
        "file": "aws-topology.json", "status": topology["status"],
        "pattern": topology["pattern"],
        "nodes": topology["counts"]["nodes"],
        "edges": topology["counts"]["edges"],
        "high_availability_proposed": topology["high_availability_proposed"],
        "review_required": len(topology["review_required"]),
    }
    # AWS 패턴별 적합 조건/제외 근거는 AI와 독립된 재현 가능한 의사결정 매트릭스로 생성합니다.
    decision_matrix = compare_architectures(result, profile, requirements, contract, topology)
    result["decision_matrix"] = {
        "file": "architecture-decision-matrix.json",
        "status": decision_matrix["status"],
        "selected_reference": decision_matrix["selected_reference"],
        "alternative_candidates": decision_matrix["alternative_candidates"],
        "approved": False,
    }
    # 선택적 AI 검토는 기존 결정 규칙의 결과와 실제 AWS 다이어그램을 바꾸지 않습니다.
    ai_review = review_architecture(
        profile, graph, requirements, result,
        enabled=ai_enabled, api_key=os.environ.get("OPENAI_API_KEY"),
        model=ai_model, explicit_requirements=explicit_fields,
    )
    result["ai_review"] = {
        "status": ai_review["status"], "file": "ai-review.json",
        "authoritative": False,
    }
    # 모델의 의견을 자동 적용하지 않고 규칙 기반 참조안과 사용자 요구를 독립적으로 검사.
    validation = validate_architecture(result, profile, requirements, graph, ai_review)
    if decision_matrix["status"] == "blocked_for_review":
        validation["findings"].append({
            "rule_id": "DEC-001", "pillar": "운영 우수성", "severity": "blocker",
            "title": "현재 AWS 참조안의 명시적 조건 충돌",
            "detail": "아키텍처 후보 비교에서 현재 참조안에 적용 불가 조건이 발견되었습니다.",
            "evidence": ["architecture-decision-matrix.json"],
            "recommended_action": "현재 참조안과 블로커를 검토하고 다른 실행 전략을 사용자 승인으로 결정하세요.",
            "verification": "정적 선택 규칙이며 실제 AWS 검증 결과가 아닙니다.",
        })
        validation["counts"]["blocker"] += 1
        validation["decision_gate"] = "blocked"
        topology["status"] = "blocked_for_review"
        result["aws_topology"]["status"] = "blocked_for_review"
    if validation["decision_gate"] == "blocked" or any(
        x["id"] == "NET-SSR-CONFLICT" for x in topology["review_required"]
    ):
        topology["status"] = "blocked_for_review"
        result["aws_topology"]["status"] = "blocked_for_review"
    result["validation"] = {
        "file": "validation.json",
        "decision_gate": validation["decision_gate"],
        "production_ready": False,
        "blockers": validation["counts"]["blocker"],
        "review_required": validation["counts"]["review_required"],
    }
    # 비용은 요금 출처와 사용량이 명시된 경우만 계산하며, 누락 단가는 0으로 처리하지 않음.
    cost_report = estimate_costs(read_cost_inputs(root, cost_input), live=live_pricing)
    # Terraform plan 파일은 민감 원문을 포함할 수 있어 결과에는 익명화된 위험만 기록.
    iac_report = inspect_terraform_plan(read_terraform_plan(root, terraform_plan))
    result["cost_estimate"] = {
        "file": "cost-estimate.json",
        "status": cost_report["status"], "monthly_total_usd": cost_report["monthly_total_usd"],
        "complete": cost_report["complete"],
    }
    result["iac_review"] = {
        "file": "iac-policy.json",
        "status": iac_report["status"], "critical_findings": iac_report["counts"]["critical"],
        "production_ready": False,
    }
    result["application_graph"] = {
        "file": "application-graph.json",
        "source_files": graph["scanned_source_files"],
        "nodes": graph["counts"]["nodes"],
        "edges": graph["counts"]["edges"],
        "parser_errors": len(graph["errors"]),
        "incomplete": graph["scan_truncated"] or bool(graph["errors"]),
    }
    out = Path(output).resolve()
    if out == root or out == root.parent:
        raise ValueError("보고서 경로는 저장소 루트 또는 상위 폴더일 수 없습니다.")
    out.mkdir(parents=True, exist_ok=True)
    diagram_info = render_application_diagram(graph, out)
    topology_diagram = render_aws_topology(topology, out)
    result["aws_topology"]["embedded_icons"] = topology_diagram["embedded_icons"]
    result["application_graph"]["diagram"] = diagram_info
    for name, value in (
        ("application-graph.json", graph),
        ("aws-topology.json", topology),
        ("architecture-decision-matrix.json", decision_matrix),
        ("evidence-contract.json", contract),
        ("requirements-gaps.json", {
            "schema_version": "1.0",
            "questions": contract["unknowns"], "analysis_status": contract["status"],
        }),
        ("ai-review.json", ai_review),
        ("cost-estimate.json", cost_report),
        ("iac-policy.json", iac_report),
        ("validation.json", validation),
        ("repository-analysis.json", profile),
        ("requirements-used.json", requirements),
        ("architecture.json", result),
    ):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    (out / "ai-review.md").write_text(markdown_ai_review(ai_review), encoding="utf-8")
    (out / "evidence-report.md").write_text(markdown_evidence(contract), encoding="utf-8")
    (out / "aws-topology.md").write_text(markdown_topology(topology), encoding="utf-8")
    (out / "network-policy.md").write_text(markdown_network_policy(topology), encoding="utf-8")
    (out / "architecture-decision-matrix.md").write_text(markdown_decision_matrix(decision_matrix), encoding="utf-8")
    (out / "cost-estimate.md").write_text(markdown_cost(cost_report), encoding="utf-8")
    (out / "iac-policy.md").write_text(markdown_iac(iac_report), encoding="utf-8")
    (out / "validation.md").write_text(markdown_validation(validation), encoding="utf-8")
    (out / "decision-record.md").write_text(markdown_adr(result, validation), encoding="utf-8")
    report = markdown_report(result)
    report += "\n## 9. 코드 기반 애플리케이션 그래프 (추가 산출물)\n\n"
    report += "- 분석 파일 수: " + str(graph["scanned_source_files"]) + "\n"
    report += "- API: " + str(graph["counts"]["nodes"].get("route", 0))
    report += " / 함수·메서드: " + str(graph["counts"]["nodes"].get("function", 0))
    report += " / 데이터 모델 정의: " + str(graph["counts"]["nodes"].get("model", 0)) + "\n"
    report += "- 확인된 호출 연결: " + str(graph["counts"]["edges"].get("calls", 0)) + "\n"
    report += "- 산출물: `application-graph.json`, `application-graph.svg`, `application-graph.png`, `application-graph.dot`\n"
    if graph["errors"]:
        report += "- **일부 소스 미분석**: " + str(len(graph["errors"])) + "건. JSON의 errors 필드를 확인해주세요.\n"
    if diagram_info["visualization_truncated"]:
        report += "- **그림 크기 제한**: 일부 관계는 그림에서 생략되었습니다. 전체 근거는 JSON을 확인하세요.\n"
    report += "\n> 이 그림은 코드 구문에서 확인된 의존 관계이며 운영 환경의 실제 네트워크 흐름을 증명하지 않습니다.\n"
    report += "\n## 10. AI 솔루션 아키텍처 보조 검토\n\n"
    report += "- 상태: " + ai_review["status"] + "\n"
    report += "- 상세: `ai-review.md`, `ai-review.json` (AI를 사용하지 않아도 상태 파일 생성)\n"
    report += "- AI가 제안한 대안은 기본 설계도와 분리되며 자동 승인·반영되지 않습니다.\n"
    report += "\n## 11. 아키텍처 정적 제약 검토와 결정 기록\n\n"
    report += "- 검토 상태: " + validation["decision_gate"] + "\n"
    report += "- 차단 항목: " + str(validation["counts"]["blocker"]) + "\n"
    report += "- 수동 확인 항목: " + str(validation["counts"]["review_required"]) + "\n"
    report += "- 상세: `validation.json`, `validation.md`, `decision-record.md`\n"
    report += "- 모든 Well-Architected 항목은 실환경 검증 전이며 운영 적합성을 보증하지 않습니다.\n"
    report += "\n## 12. 비용 시나리오 및 IaC 보안 검토 (별도 산출물)\n\n"
    report += "- 비용 산정: " + cost_report["status"] + " (cost-estimate.json/md)\n"
    report += "- Terraform 계획 검사: " + iac_report["status"] + " (iac-policy.json/md)\n"
    report += "- IaC 명시적 보안 위험: " + str(iac_report["counts"]["critical"]) + "건\n"
    report += "- 비용·보안 검사 미실행을 통과로 표시하지 않습니다.\n"
    report += "\n## 13. 코드 관찰 사실과 추가 요구사항\n\n"
    report += "- 정적 관찰 근거: " + str(len(contract["observations"])) + "건\n"
    report += "- 설정 기반 추정 단서: " + str(len(contract["configuration_inferences"])) + "건\n"
    report += "- 사용자가 명시한 요구사항: " + str(len(contract["user_requirements"])) + "건\n"
    report += "- 확인 질문: " + str(len(contract["unknowns"])) + "건\n"
    report += "- 상세: `evidence-contract.json`, `evidence-report.md`, `requirements-gaps.json`\n"
    if contract["status"] == "partial":
        report += "- **주의**: 일부 코드 분석 실패가 발생해 미관측 요소를 없는 것으로 단정할 수 없습니다.\n"
    report += "\n## 14. AWS To-Be 네트워크·서비스 토폴로지 (신규 제안)\n\n"
    report += "- 상세 영역/서비스 노드: " + str(topology["counts"]["nodes"]) + "\n"
    report += "- 네트워크/서비스 연결: " + str(topology["counts"]["edges"]) + "\n"
    report += "- 구축 전 추가 확인: " + str(len(topology["review_required"])) + "건\n"
    report += "- 파일: `aws-topology.json`, `aws-topology.md`, `aws-topology.svg/png/dot`\n"
    report += "- AZ/서브넷·네트워크·서비스 연결은 가정된 참조 구조입니다. 실환경 정책과 리소스를 확인한 결과가 아닙니다.\n"
    report += "\n## 15. AWS 서비스별 선정·제외 근거 (대안 비교)\n\n"
    report += "- 현재 참조 실행 유형: " + decision_matrix["selected_reference"] + "\n"
    report += "- 선택 검토 상태: " + decision_matrix["status"] + "\n"
    report += "- 추가 검토 후보: " + ", ".join(decision_matrix["alternative_candidates"]) + "\n"
    report += "- 파일: `architecture-decision-matrix.json/md` (EC2 포함, 선택 자동 변경 없음)\n"
    report += "- AWS 서비스별 실제 성능·비용·가용성 검증 없이 후보 간 정량 순위를 산정하지 않습니다.\n"
    (out / "recommendation.md").write_text(report, encoding="utf-8")

    if __package__:
        from .render_aws_icons import render_icon_diagram
    else:
        from render_aws_icons import render_icon_diagram
    render_icon_diagram(result, out)
    print(report)
    return result


def main():
    parser = argparse.ArgumentParser(description="AWS 아키텍처 분석 및 제안 (배포 없음)")
    parser.add_argument("--repo", default=".", help="분석할 GitHub 저장소 경로")
    parser.add_argument("--output", default="architecture-output", help="결과물 출력 디렉터리")
    parser.add_argument("--workload", choices=["auto", "web", "backend", "mobile"], default="auto")
    parser.add_argument("--budget", type=float, default=None, help="사용자 입력 월 예산(USD): 비용 추정치 아님")
    parser.add_argument("--requirements", default=None, help="저장소 내부 JSON 요구사항 파일")
    parser.add_argument("--enable-ai", action="store_true",
                        help="외부 OpenAI API로 비기밀 구조화 분석 근거를 전송합니다 (명시적 동의 필요)")
    parser.add_argument("--ai-model", default="gpt-6-luna", help="지원되는 Responses API 모델 ID")
    parser.add_argument("--cost-input", default=None, help="비기밀 월 사용량과 단가 출처 JSON (선택)")
    parser.add_argument("--live-pricing", action="store_true", help="AWS Price List API 실시간 조회 (명시적 활성화, 읽기 권한 필요)")
    parser.add_argument("--terraform-plan", default=None, help="terraform show -json으로 만든 로컬 plan JSON 파일 (민감 정보 포함 주의)")
    args = parser.parse_args()
    try:
        run(args.repo, args.output, args.workload, args.budget, args.requirements,
            args.enable_ai, args.ai_model, args.cost_input,
            args.live_pricing, args.terraform_plan)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
