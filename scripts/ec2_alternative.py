"""EC2 배포 대안의 논리 To-Be 설계. 원안 Fargate를 변경하지 않습니다.

기존 subnet 구조에서 비교용 네트워크 범위만 재사용합니다.
ECS Fargate용 ECR/VPC Endpoint/NAT 정책은 EC2 대안에 복사하지 않습니다.
"""
from copy import deepcopy


def design_ec2_alternative(topology, requirements):
    if topology["pattern"] != "containers":
        return None
    # 저장소 코드/실제 AWS 실행 검증 없이 '대안'만 제시합니다.
    selected = {"client", "aws", "observability", "vpc", "alb", "waf",
                "az_a", "az_b", "public_a", "public_b", "app_a", "app_b",
                "db_a", "db_b", "db_subnet_group", "rds", "rds_standby", "igw"}
    new_nodes = [deepcopy(n) for n in topology["nodes"] if n["id"] in selected]
    present = {x["id"] for x in new_nodes}
    new_edges = [deepcopy(e) for e in topology["edges"]
                 if e["source"] in present and e["target"] in present and
                 e["kind"] not in ("dependency", "routing_proposal")]
    def node(ident, name, kind, parent):
        new_nodes.append({
            "id": ident, "name": name, "kind": kind,
            "parent": parent, "evidence_ids": [], "basis": "alternative_only",
            "status": "proposed_not_deployed",
            "design_rule_ids": ["T-BASE", "T-ALB"],
        })
    def edge(a, b, label, kind):
        new_edges.append({
            "source": a, "target": b, "purpose": label, "kind": kind,
            "evidence_ids": [], "design_rule_ids": ["T-BASE", "T-ALB"],
            "status": "proposed_not_verified",
        })
    node("asg", "EC2 Auto Scaling Group (선정 전)", "management", "vpc")
    ha = topology["high_availability_proposed"]
    for az in ("a", "b") if ha else ("a",):
        node("ec2_" + az, "Amazon EC2 · 논리 AZ-" + az.upper(), "compute", "app_" + az)
        edge("asg", "ec2_" + az, "EC2 인스턴스 수·타입/AMI 미확정", "placement")
        edge("alb", "ec2_" + az, "ALB target group · 앱 포트/헬스체크 미확정", "traffic")
        edge("ec2_" + az, "observability", "EC2 CloudWatch 지표/로그 별도 설정 필요", "telemetry")
        if "rds" in present:
            edge("ec2_" + az, "rds", "EC2 SG→RDS SG DB 포트 검토", "traffic")

    reviews = [
        {"id": "EC2-ASG", "title": "Auto Scaling 정책 미확정",
         "action": "EC2 타입/AMI, Launch Template, Desired/Min/Max, CPU/요청량 지표와 ALB 타깃 그룹을 별도 검증하세요."},
        {"id": "EC2-PATCH", "title": "OS 운영·보안 패치 책임",
         "action": "IAM 인스턴스 프로파일, Systems Manager/패치, OS 업데이트, AMI 교체·롤백, CloudWatch Agent를 설계하세요."},
        {"id": "EC2-EGRESS", "title": "사설 서브넷 outbound 재설계 필요",
         "action": "Fargate의 ECR/VPC Endpoint 가정은 재사용하지 않습니다. OS 패치·SSM·외부 API 통신에 필요한 NAT/Endpoint 정책을 검증하세요."},
        {"id": "EC2-OPERATIONS", "title": "인프라 운영 부담 및 비용",
         "action": "EBS·백업·정지 인스턴스·AMI 비용, 보안 업데이트, HA 인스턴스 수, SLO/부하 시험을 비교하세요."},
    ]
    if topology["alb_scheme"] == "internal":
        reviews.append({
            "id": "EC2-INTERNAL", "title": "내부 ALB 접근 방식",
            "action": "내부 클라이언트 및 VPN/전용망 접근 경로를 확인하세요.",
        })
    if not requirements.get("container_port"):
        reviews.append({
            "id": "EC2-APP-PORT", "title": "애플리케이션 포트 미확정",
            "action": "EC2 앱 수신 포트와 ALB 타깃 그룹/SG/헬스체크를 일치시키세요.",
        })
    return {
        "schema_version": "1.0", "status": "alternative_proposed_unverified",
        "pattern": "ec2_alternative",
        "region": topology["region"],
        "region_confirmed": topology["region_confirmed"],
        "symbolic_azs": list(topology["symbolic_azs"]),
        "high_availability_proposed": ha,
        "nodes": new_nodes, "edges": new_edges,
        "review_required": reviews,
        "alb_scheme": topology["alb_scheme"],
        "egress_strategy": "undecided_for_ec2",
        "network_controls": [{
            "id": "EC2-SG-ALB", "source": "alb", "target": "ec2",
            "protocol": "TCP", "port": requirements.get("container_port"),
            "source_scope": "ALB Security Group만",
            "status": "proposed_not_applied",
        }],
        "route_intents": [],
        "rule_catalog": topology["rule_catalog"],
        "assumptions": [
            "현재 ECS Fargate 기준 참조안을 변경하거나 자동 배포하지 않습니다.",
            "EC2 Auto Scaling Group·인스턴스는 논리 제안이며 실제 수량/AMI/인스턴스 타입은 검증하지 않았습니다.",
            "Fargate용 NAT/VPC Endpoint 정책을 EC2에서 재사용하지 않으며 별도 아웃바운드 정책이 필요합니다.",
        ],
        "counts": {"nodes": len(new_nodes), "edges": len(new_edges),
                   "security_controls": 1, "route_intents": 0},
        "approved": False,
    }


def markdown_ec2_alternative(value):
    if value is None:
        return "# EC2 대안 검토\n\n현재 선택된 참조안은 컨테이너가 아니므로 EC2 네트워크 대안은 생성하지 않습니다.\n"
    rows=[
        "# EC2 Auto Scaling 대안 (검토용)", "",
        "> **현재 선택된 Fargate 설계 변경 없음.** EC2 인스턴스를 배포하거나 계정에 접속하지 않습니다.",
        "", "- 공개 범위: " + value["alb_scheme"],
        "- 고가용성: " + ("다중 논리 AZ 제안" if value["high_availability_proposed"] else "추가 검토 필요"),
        "- SG 앱 포트: " + (str(value["network_controls"][0]["port"])
                           if value["network_controls"][0]["port"] else "사용자 확인 필요"),
        "- NAT/VPC Endpoint: EC2에서 별도 확인 필요", "",
        "## EC2 선택 시 운영 책임", "",
    ]
    rows.extend("- [" + issue["id"] + "] " + issue["title"] +
                ": " + issue["action"] for issue in value["review_required"])
    rows += ["", "## 승인 및 검증", "",
             "- 현재 대안은 미승인이며 운영 정책/IAM/실제 RTO/RPO/비용 실측 없이 선택할 수 없습니다.",
             "- EC2와 ECS Fargate의 네트워크, 패치, 비용은 동일한 것으로 간주하지 않습니다.", ""]
    return "\n".join(rows)
