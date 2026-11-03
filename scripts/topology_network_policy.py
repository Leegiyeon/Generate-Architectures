"""AWS 설계 후보의 접근 경계·Private outbound 경로와 근거 규칙.

서비스 정보는 참조 설계이며 실제 AWS 리소스/권한을 만들거나 조회하지 않습니다.
프로젝트 요구에 없는 NAT/VPC Endpoint를 실제 구성처럼 확정하지 않습니다.
"""
from copy import deepcopy

RULES = {
    "T-BASE": {
        "title": "제안 모델 / 실제 구성 미검증",
        "url": None,
        "note": "노드와 연결은 논리적인 설계 후보이며 실제 AWS 자원 존재의 증거가 아닙니다.",
    },
    "T-ALB": {
        "title": "ALB 다중 AZ 서브넷/타깃/보안 경계",
        "url": "https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-application-load-balancer.html",
        "note": "표준 AZ 기반 ALB는 서로 다른 2개 AZ 서브넷을 요구하며 타깃과 SG/헬스체크도 검증해야 합니다.",
    },
    "T-VPC": {
        "title": "VPC 및 Public/Private subnet 논리 분리",
        "url": "https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Subnets.html",
        "note": "실제 CIDR·라우팅·NACL/SG·엔드포인트·IPv4/IPv6는 별도 검증해야 합니다.",
    },
    "T-FARGATE": {
        "title": "Private Fargate 네트워크와 인터넷/엔드포인트 필요",
        "url": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html",
        "note": "Private 태스크는 ECR pull/로그/비밀정보/외부 API에 필요한 경로를 확보해야 합니다.",
    },
    "T-EGRESS": {
        "title": "NAT Gateway / VPC Endpoint 선택",
        "url": "https://repost.aws/knowledge-center/ecs-fargate-tasks-private-subnet",
        "note": "NAT는 아웃바운드 인터넷, VPC Endpoint는 지원 서비스의 사설 연결. 포괄적인 대체재가 아닙니다.",
    },
    "T-RDS": {
        "title": "RDS DB subnet group 및 보안 접근",
        "url": "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html",
        "note": "DB 엔진, Primary/Standby, private subnet, SG, 백업·RTO/RPO를 확인해야 합니다.",
    },
    "T-CLOUDFRONT": {
        "title": "CloudFront 비공개 S3 오리진과 OAC",
        "url": "https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html",
        "note": "S3 웹사이트 엔드포인트에는 OAC를 적용하지 않습니다. 일반 버킷 오리진·서명·정책이 필요합니다.",
    },
    "T-LAMBDA": {
        "title": "Lambda와 VPC 연결의 선택적 적용",
        "url": "https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html",
        "note": "Lambda는 VPC 리소스 접근이 필요한 경우에만 VPC 연결을 검토합니다.",
    },
    "T-OBS": {
        "title": "모니터링 설정 제안",
        "url": None,
        "note": "로그, 경보, 보관, 예산은 별도 검토하며 CloudWatch 실제 활성화는 미확인입니다.",
    },
    "T-SG": {
        "title": "최소 권한 네트워크 접근 의도",
        "url": "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html",
        "note": "SG 규칙은 제안일 뿐 API 호출/콘솔 정책 조회로 검증되지 않았습니다.",
    },
}


def enrich_topology(topology, requirements, contract):
    """기존 AWS 토폴로지에 임의 IP 없이 SG/라우트 의도와 서비스 근거를 추가."""
    result = deepcopy(topology)
    if result["status"] != "proposed_unverified":
        raise ValueError("이미 확정되거나 수정된 토폴로지에 중복 정책 적용 불가")
    nodes = {x["id"]: x for x in result["nodes"]}
    edges = result["edges"]
    issues = result["review_required"]
    policies = []
    routes = []
    req_ids = {r["key"]: r["id"] for r in contract.get("user_requirements", [])}
    explicit_keys = set(req_ids)
    pattern = result["pattern"]
    is_containers = pattern == "containers"
    scheme = requirements.get("alb_scheme", "internet_facing")
    egress = requirements.get("egress_strategy", "undecided")
    external = requirements.get("external_outbound_required")
    ha = result["high_availability_proposed"]

    def add_node(identifier, label, kind, parent, rule):
        if identifier in nodes or (parent and parent not in nodes):
            raise ValueError("토폴로지 노드가 중복되거나 부모가 없습니다.")
        n = {
            "id": identifier, "name": label, "kind": kind, "parent": parent,
            "basis": "explicit_choice_proposal", "status": "proposed_not_deployed",
            "evidence_ids": [req_ids["egress_strategy"]] if "egress_strategy" in req_ids else [],
            "design_rule_ids": ["T-BASE", rule],
        }
        nodes[identifier] = n
        result["nodes"].append(n)

    def add_edge(src, target, purpose, kind, rule):
        if src not in nodes or target not in nodes:
            raise ValueError("존재하지 않는 노드 간 제안 연결")
        edges.append({
            "source": src, "target": target, "purpose": purpose, "kind": kind,
            "status": "proposed_not_verified",
            "evidence_ids": [req_ids["egress_strategy"]] if "egress_strategy" in req_ids else [],
            "design_rule_ids": ["T-BASE", rule],
        })

    def add_review(ident, title, action):
        if not any(x["id"] == ident for x in issues):
            issues.append({"id": ident, "title": title, "action": action})

    def add_control(identifier, src, dst, port, source_scope, title):
        ref_keys = ("alb_scheme", "container_port", "database_port")
        policies.append({
            "id": identifier, "from": src, "to": dst,
            "protocol": "TCP", "port": port,
            "source_scope": source_scope,
            "description": title,
            "status": "proposed_not_applied",
            "evidence_ids": [req_ids[k] for k in ref_keys if k in req_ids],
            "design_rule_ids": ["T-SG"],
        })

    def add_route(identifier, src, dst, role, complete=False):
        routes.append({
            "id": identifier, "source": src, "target": dst,
            "purpose": role, "status": "proposal_requires_route_table_check",
            "validated": False,
            "destination_cidr": None, "next_hop_resource_id": None,
            "fully_specified": complete, "design_rule_ids": ["T-VPC", "T-EGRESS"],
        })

    # 모든 서비스·연결선이 규칙/가정에 대한 추적 ID를 가지도록 합니다.
    for item in result["nodes"]:
        if "design_rule_ids" not in item:
            rule = "T-BASE"
            if item["kind"] in ("vpc", "az", "subnet_public",
                                "subnet_private", "subnet_database"):
                rule = "T-VPC"
            elif item["id"] in ("alb", "waf"):
                rule = "T-ALB"
            elif item["id"].startswith("task_"):
                rule = "T-FARGATE"
            elif item["id"] in ("db_subnet_group", "rds", "rds_standby"):
                rule = "T-RDS"
            elif item["id"] in ("cdn", "bucket", "oac"):
                rule = "T-CLOUDFRONT"
            elif item["id"] in ("lambda", "api"):
                rule = "T-LAMBDA"
            elif item["id"] == "observability":
                rule = "T-OBS"
            item["design_rule_ids"] = ["T-BASE", rule]
    for item in edges:
        if "design_rule_ids" not in item:
            rule = "T-BASE"
            if item["kind"] in ("placement", "trust_boundary"):
                rule = "T-VPC"
            elif item["kind"] == "replication":
                rule = "T-RDS"
            elif item["kind"] == "telemetry":
                rule = "T-OBS"
            elif item["source"] in ("cdn", "bucket", "oac"):
                rule = "T-CLOUDFRONT"
            elif item["source"] in ("lambda", "api"):
                rule = "T-LAMBDA"
            elif item["source"] == "alb":
                rule = "T-ALB"
            item["design_rule_ids"] = ["T-BASE", rule]

    if is_containers:
        if scheme not in ("internal", "internet_facing"):
            raise ValueError("지원하지 않는 ALB 접근 범위")
        if egress not in ("undecided", "nat_gateway", "vpc_endpoints_only",
                          "nat_plus_endpoints"):
            raise ValueError("지원하지 않는 Private outbound 방식")

        # 인터넷으로 공개하는 ALB에만 IGW를 반드시 표현합니다.
        # 내부 ALB는 외부 호출자->Internal ALB의 네트워크 경로를 확정하지 않습니다.
        need_igw = scheme == "internet_facing" or egress in (
            "nat_gateway", "nat_plus_endpoints")
        if need_igw:
            add_node("igw", "Internet Gateway (VPC 연결 제안)", "network", "vpc", "T-VPC")
        if scheme == "internet_facing":
            direct = next((e for e in edges if e["source"] == "client"
                           and e["target"] == "alb"), None)
            if direct is None:
                raise ValueError("공개 ALB 인입 근거가 없습니다.")
            edges.remove(direct)
            add_edge("client", "igw", "공개 HTTPS 인입 논리 경로", "traffic", "T-ALB")
            add_edge("igw", "alb", "ALB 공용 서브넷 접근 제안", "traffic", "T-ALB")
            for az in ("a", "b"):
                add_route("PUBLIC-ROUTE-" + az.upper(), "public_" + az, "igw",
                          "Public ALB용 인터넷 게이트웨이 경로 검토")
        else:
            add_review("NET-INTERNAL-ALB", "Internal ALB는 외부 인터넷 직접 접근 불가",
                       "연결 클라이언트의 사설 VPC/VPN/DX/TGW/Peering 경로와 권한을 확인하세요.")

        add_control("SG-ALB-443", "client", "alb", 443,
                    "public_https" if scheme == "internet_facing" else "private_client",
                    "ALB의 HTTPS 리스너 접근 제안, TLS/ACM 및 공개 범위 확인 필요")
        app_port = requirements.get("container_port")
        db_port = requirements.get("database_port")
        for az in ("a", "b") if ha else ("a",):
            task = "task_" + az
            add_control("SG-APP-" + az.upper(), "alb", task, app_port,
                        "alb_sg_only",
                        "ALB Security Group에서만 ECS 대상그룹 포트 허용")
            if "rds" in nodes:
                add_control("SG-DB-" + az.upper(), task, "rds", db_port,
                            "ecs_sg_only", "ECS Security Group에서만 DB 포트 접근")
        if not app_port:
            add_review("NET-APP-PORT", "ECS 앱 포트가 미확정",
                       "container_port를 확인하고 ALB 대상그룹/헬스체크 및 SG 포트를 구성하세요.")
        if "rds" in nodes and not db_port:
            add_review("NET-DB-PORT", "RDS 포트·엔진 미확정",
                       "DB 엔진과 database_port를 확인하고 앱 SG에 한정해 접근을 검증하세요.")

        if egress == "undecided":
            for az in ("a", "b") if ha else ("a",):
                add_route("APP-OUTBOUND-" + az.upper(), "app_" + az, "not_selected",
                          "ECR/로그/시크릿/외부 API에 필요한 outbound 경로 미결정")
            add_review("NET-EGRESS-CHOICE", "Private App Subnet의 outbound 전략 선택 필요",
                       "egress_strategy=nat_gateway / vpc_endpoints_only / nat_plus_endpoints 중 선택하세요. 인터넷 호출 필요 여부도 확인하세요.")
        elif egress in ("nat_gateway", "nat_plus_endpoints"):
            selected = ("a", "b") if ha else ("a",)
            for az in selected:
                add_node("nat_" + az, "NAT Gateway (AZ-" + az.upper() +
                         ", 공인 IP·비용 확인)", "network", "public_" + az, "T-EGRESS")
                add_edge("nat_" + az, "igw", "아웃바운드 인터넷 경로 제안",
                         "routing_proposal", "T-EGRESS")
            for az in selected:
                add_route("APP-NAT-" + az.upper(), "app_" + az, "nat_" + az,
                          "Private 앱 아웃바운드 → 같은 AZ NAT 경로 검토")
                add_edge("task_" + az, "nat_" + az, "작업 아웃바운드 경로 제안",
                         "routing_proposal", "T-EGRESS")
            add_review("NET-NAT-COST", "NAT Gateway EIP/요금/가용성이 미확정",
                       "AZ별 NAT 비용, 트래픽/데이터 전송 및 탄력적 IP와 단일 AZ 장애 영향을 확인하세요.")

        if egress in ("vpc_endpoints_only", "nat_plus_endpoints"):
            endpoints = (
                ("ecr_api", "ECR API Interface Endpoint (검토)"),
                ("ecr_dkr", "ECR Docker Interface Endpoint (검토)"),
                ("s3_gateway", "S3 Gateway Endpoint (검토)"),
                ("logs", "CloudWatch Logs Interface Endpoint (검토)"),
                ("secrets", "Secrets Manager Interface Endpoint (사용 시)"),
            )
            for key, label in endpoints:
                add_node("vpce_" + key, label, "network", "vpc", "T-EGRESS")
                # 그림에는 필수/선택 인터페이스의 '검토'만 나타내고 실제 연결은 확정하지 않음.
                for az in ("a", "b") if ha else ("a",):
                    add_edge("task_" + az, "vpce_" + key,
                             "VPC Endpoint 접근 정책·Private DNS·SG 확인",
                             "dependency", "T-EGRESS")
            add_review("NET-VPCE-ENDPOINTS", "Endpoint 접근 조건/필요 서비스 검증",
                       "ECR API/DKR, S3 gateway, CloudWatch Logs, Secrets Manager 등 실제 기능·리전·서브넷·Private DNS·정책·SG를 검토하세요.")

        if external is True and egress == "vpc_endpoints_only":
            add_review("NET-EGRESS-CONFLICT", "외부 인터넷 API와 endpoint-only 전략 충돌",
                       "일반 외부 인터넷 호출은 AWS 서비스 VPC Endpoint만으로 충족되지 않습니다. NAT/프록시/IPv6 경로 등 별도 정책을 설계하세요.")
            result["status"] = "blocked_for_review"
        elif external is None:
            add_review("NET-EXTERNAL-UNKNOWN", "외부 API 호출 필요 여부 미확정",
                       "external_outbound_required를 입력하여 Private App Subnet의 아웃바운드 정책을 확정하세요.")
        if egress != "undecided":
            add_review("NET-ROUTE-VERIFY", "제안한 라우트는 실제 연결 보증이 아님",
                       "실제 VPC route table, NACL, SG, AZ별 Endpoint/NAT 배치 및 IAM 권한을 확인하세요.")

    # 기존 단순 그래프를 포함한 전체 제안의 출처를 검사합니다. 룰 미지원이면 실패시킵니다.
    valid_ids = {x["id"] for x in contract.get("user_requirements", [])}
    valid_ids |= {x["id"] for x in contract.get("observations", [])}
    for entry in result["nodes"] + edges:
        if not entry.get("design_rule_ids") or any(k not in RULES for k in entry["design_rule_ids"]):
            raise ValueError("설계 노드/연결에 출처가 없는 규칙")
        if set(entry.get("evidence_ids", ())) - valid_ids:
            raise ValueError("설계 노드/연결에 잘못된 코드/요구사항 근거")
    result["network_controls"] = policies
    result["route_intents"] = routes
    result["egress_strategy"] = egress if is_containers else "not_applicable"
    result["alb_scheme"] = scheme if is_containers else "not_applicable"
    result["rule_catalog"] = RULES
    result["counts"] = {"nodes":len(result["nodes"]), "edges":len(result["edges"]),
                         "security_controls":len(policies), "route_intents":len(routes)}
    return result


def markdown_network_policy(topology):
    """사용자/검토자가 AWS 설계 가정을 네트워크 경계별로 확인합니다."""
    lines = ["# AWS 네트워크 접근 및 Private Outbound 설계 제안", "",
             "> 모든 설정은 제안/미검증이며 실제 Security Group 및 Route Table이 아닙니다.",
             "", "- ALB: " + topology["alb_scheme"],
             "- Private outbound: " + topology["egress_strategy"], "",
             "## Security Group 접근 의도", "",
             "| ID | 경계 | TCP 포트 | 접근 범위 |",
             "| --- | --- | --- | --- |"]
    for sg in topology["network_controls"]:
        port = str(sg["port"]) if sg["port"] is not None else "미확정"
        lines.append("| " + sg["id"] + " | " + sg["from"] + " → " + sg["to"] +
                     " | " + port + " | " + sg["source_scope"] + " |")
    if not topology["network_controls"]:
        lines.append("| 해당 없음 | SG 기반 설계 대상 없음 | - | - |")
    lines += ["", "## Route Table / Private outbound 의도", "",
              "| ID | 출발지 | 대상 | 상태 |",
              "| --- | --- | --- | --- |"]
    for route in topology["route_intents"]:
        lines.append("| " + route["id"] + " | " + route["source"] + " | " +
                     route["target"] + " | " + route["status"] + " |")
    if not topology["route_intents"]:
        lines.append("| 해당 없음 | 해당 없음 | 해당 없음 | 해당 없음 |")
    lines += ["", "## 제안 설계 근거 및 공식 참조", ""]
    used = {ref for node in topology["nodes"] + topology["edges"]
            for ref in node["design_rule_ids"]}
    for ref in sorted(used):
        rule = topology["rule_catalog"][ref]
        lines.append("- " + ref + ": " + rule["title"] + " — " + rule["note"] +
                     ((" (" + rule["url"] + ")") if rule["url"] else ""))
    lines += ["", "## 확인되지 않은 정보", ""]
    lines.extend("- [" + x["id"] + "] " + x["title"] + ": " + x["action"]
                 for x in topology["review_required"])
    return "\n".join(lines) + "\n"
