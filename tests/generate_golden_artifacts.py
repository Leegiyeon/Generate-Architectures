"""10개 가상 대표 프로젝트의 결과물을 사람이 시각적으로 확인할 수 있도록 생성.

실제 운영 코드·AWS 계정·시크릿 접근 없이 tests/test_golden_workloads.py의
고정 fixture만 사용합니다. 디렉터리는 사용자 검토를 위한 로컬 출력입니다.
"""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import sys

# CLI로 직접 실행할 때도 저장소 루트의 scripts 패키지를 불러옵니다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_golden_workloads import CASES
from scripts.recommend_architecture import run


def main():
    parser=argparse.ArgumentParser(description="10개 골든 가상 프로젝트 시각 QA 파일 생성 (배포 없음)")
    parser.add_argument("--output",default="golden-output",
                        help="리포트 출력 폴더 (기본 golden-output)")
    args=parser.parse_args()
    out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    overview=[]
    for case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo"
            root.mkdir()
            for rel,content in case["files"].items():
                path=root/rel
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding="utf-8")
            requirement_file=None
            if case.get("requirements"):
                requirement_file="req.json"
                (root/requirement_file).write_text(
                    json.dumps(case["requirements"]),encoding="utf-8")
            workspace=Path(tmp)/"analysis"
            with redirect_stdout(io.StringIO()):
                result=run(root,workspace,requirements_file=requirement_file)
            if result["option_id"] != case["expected"]:
                raise ValueError("골든 fixture 예상 패턴과 실제 실행이 불일치: "+case["id"])
            dst=out/case["id"]
            dst.mkdir(parents=True,exist_ok=True)
            # 한 장 시각 QA에 필요한 파일만 모으되 SVG/PNG는 동일 실행에서 복사합니다.
            for name in ("START-HERE.html","START-HERE.md","aws-topology.svg",
                         "aws-topology.png","application-graph.svg",
                         "validation.md","architecture.json"):
                shutil.copyfile(workspace/name,dst/name)
            (dst/"deliverables").mkdir(exist_ok=True)
            for name in ("01-aws-to-be.svg","01-aws-to-be.png",
                         "02-architecture-decisions.md",
                         "03-security-operations.md","04-cost-capacity.md"):
                shutil.copyfile(workspace/"deliverables"/name,dst/"deliverables"/name)
            # HTML 내부의 각 링크를 정상 열 수 있도록 필요한 참조파일을 추가합니다.
            for name in ("aws-topology.json","data-access-decision.md",
                         "network-policy.md","evidence-report.md",
                         "recommendation.md","artifact-index.json",
                         "cost-estimate.json"):
                shutil.copyfile(workspace/name,dst/name)
            entry={
                "id":case["id"],"expected_pattern":case["expected"],
                "detected_pattern":result["option_id"],
                "validation_gate":result["validation"]["decision_gate"],
                "topology_status":result["aws_topology"]["status"],
                "embedded_icons":result["aws_topology"]["embedded_icons"],
                "observed_sources":result["application_graph"]["source_files"],
                "parser_errors":result["application_graph"]["parser_errors"],
                "manual_visual_reviewed":False,
                "deployment_executed":False,
            }
            overview.append(entry)
    (out/"golden-index.json").write_text(json.dumps({
        "schema_version":"1.0","cases":overview,
        "manual_visual_review_completed":False,
        "aws_account_checked":False,
        "note":"생성된 10개 HTML/SVG/PNG 파일은 사람이 열어 레이아웃/문자/아이콘을 검토해야 합니다.",
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 대표 프로젝트 10종 시각 감사 (미완료 체크리스트)", "",
           "> 자동 파일 생성은 성공했지만 실제 브라우저의 한글/아이콘/잘림 품질은 사용자가 확인해야 합니다.",
           "", "| 사례 | AWS 패턴 | Browser HTML | SVG 보기 | 시각 QA 완료 |",
           "| --- | --- | --- | --- | --- |"]
    for entry in overview:
        ident=entry["id"]
        lines.append("| "+ident+" | "+entry["detected_pattern"]+
                     " | [HTML]("+ident+"/START-HERE.html) | [SVG]("+
                     ident+"/aws-topology.svg) | ☐ |")
    lines+=["", "각 사례에서 ① 한글 글자 깨짐 ② 아이콘 누락 ③ 선·라벨 클리핑/겹침 "
             "④ 모바일 확대 ⑤ 정상 링크 ⑥ As-Is/To-Be 구분 ⑦ 비용·보안 미검증 문구를 확인하세요.",
            "", "**수동 감사 완료 전 golden-index.json의 manual_visual_review_completed는 false입니다.**",
            ""]
    (out/"golden-index.md").write_text("\n".join(lines),encoding="utf-8")
    print("골든 시각 QA 산출물: "+str(out/"golden-index.md"))
    print("검토 대상: "+str(len(overview))+"개, 시각 검토 완료: 0개 (사용자 확인 필요)")


if __name__=="__main__":
    main()
