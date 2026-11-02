"""Generate Architectures: 저장소 분석 → 요구사항 검토 → 설계 대안 → 아이콘 다이어그램."""
import argparse
import json
from pathlib import Path

if __package__:
    from .repository_analyzer import inspect_repository
    from .requirements_model import parse_requirements
    from .architecture_advisor import decide, markdown_report
    from .application_graph import build_application_graph
    from .render_application_graph import render_application_diagram
else:
    from repository_analyzer import inspect_repository
    from requirements_model import parse_requirements
    from architecture_advisor import decide, markdown_report
    from application_graph import build_application_graph
    from render_application_graph import render_application_diagram


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


def run(repo, output, workload="auto", budget=None, requirements_file=None):
    """구현 범위: 읽기 전용 정적 분석 및 검토용 AWS 참조 설계 생성."""
    root = Path(repo).resolve()
    if not root.is_dir():
        raise ValueError("분석 대상 저장소가 존재하지 않습니다.")
    requirements = parse_requirements(requirements_file, root, budget, workload)
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
    result["application_graph"]["diagram"] = diagram_info
    for name, value in (
        ("application-graph.json", graph),
        ("repository-analysis.json", profile),
        ("requirements-used.json", requirements),
        ("architecture.json", result),
    ):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
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
    args = parser.parse_args()
    try:
        run(args.repo, args.output, args.workload, args.budget, args.requirements)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
