"""AWS To-Be 네트워크/서비스 참조 토폴로지 (읽기 전용 설계 제안).

VPC/서브넷/AZ는 클라우드에 배포되지 않은 논리적 구성입니다.
실제 AZ 이름·CIDR·라우팅/보안그룹·할당량·청구액은 추정하지 않습니다.
"""
from collections import Counter


def design_aws_topology(architecture, profile, requirements, contract):
    option = architecture["option_id"]
    req_refs = {r["key"]: r["id"] for r in contract["user_requirements"]}
    observed_refs = [x["id"] for x in contract["observations"]
                     if x["category"].startswith("ast_")][:10]
    region = requirements.get("region")
    ha = (requirements.get("operations_preference") == "high_availability" or
          requirements.get("availability_target_percent", 0) >= 99.9 or
          requirements.get("environment") == "production")
    db = (requirements.get("requires_relational_database") is True or
          (requirements.get("requires_relational_database") is not False and
           profile["signals"].get("relational_database") is True))
    nodes = {}
    links = []
    reviews = []

    def node(ident, label, kind, parent=None, role="design_proposal", refs=()):
        if ident in nodes:
            raise ValueError("중복 AWS 토폴로지 노드가 있습니다.")
        nodes[ident] = {
            "id": ident, "name": label, "kind": kind, "parent": parent,
            "evidence_ids": [r for r in refs if r], "basis": role,
            "status": "proposed_not_deployed",
        }

    def link(src, dst, purpose, kind="traffic", refs=()):
        if src not in nodes or dst not in nodes:
            raise ValueError("미등록된 토폴로지 서비스 연결입니다.")
        links.append({
            "source": src, "target": dst, "purpose": purpose, "kind": kind,
            "evidence_ids": [r for r in refs if r],
            "status": "proposed_not_verified",
        })

    node("client", "사용자 / 클라이언트", "client")
    node("aws", "AWS Cloud" + (" · " + region if region else " · 리전 미확정"), "boundary")
    node("observability", "CloudWatch 로그·지표 (검토 후보)", "management", "aws")
    if not region:
        reviews.append({
            "id": "NET-REGION", "title": "AWS 리전 미확정",
            "action": "리전과 데이터 보관 지역을 확정한 뒤 서비스 가용성과 비용을 재검토하세요.",
        })

    if option == "static":
        node("cdn", "CloudFront (Global)", "network", "aws")
        node("bucket", "S3 비공개 오리진", "storage", "aws")
        node("oac", "Origin Access Control (OAC)", "security", "aws")
        node("waf", "AWS WAF (정책 설계 필요)", "security", "aws")
        link("client", "cdn", "HTTPS 배포")
        link("cdn", "bucket", "서명된 오리진 요청 (OAC 적용 제안)")
        link("oac", "cdn", "OAC 설정", "policy")
        link("waf", "cdn", "Web ACL 연결 검토", "policy")
        link("cdn", "observability", "접속·에러 지표/로그 설계", "telemetry")
        reviews.append({
            "id": "NET-STATIC", "title": "S3 오리진 구성 및 인증서 미확정",
            "action": "S3 website endpoint 대신 REST bucket origin+OAC를 검토하고, ACM·DNS·버킷 정책을 확정하세요.",
        })
        if requirements.get("rendering_mode") in ("ssr", "hybrid"):
            reviews.append({
                "id": "NET-SSR-CONFLICT", "title": "정적 설계와 SSR 요구 충돌",
                "action": "SSR/서버 액션 실행 계층이 별도로 필요하므로 정적 단독 배포를 확정하지 마세요.",
            })
    elif option in ("serverless", "mobile"):
        node("api", "Amazon API Gateway (Regional)", "network", "aws")
        node("lambda", "AWS Lambda", "compute", "aws")
        link("client", "api", "HTTPS API 요청")
        link("api", "lambda", "요청 기반 함수 실행")
        link("lambda", "observability", "실행 로그·모니터링", "telemetry")
        if "DynamoDB" in architecture["nodes"]:
            node("dynamodb", "Amazon DynamoDB (데이터 모델 확인)", "database", "aws")
            link("lambda", "dynamodb", "API 데이터 접근",
                 refs=[req_refs.get("requires_persistent_storage")])
        if "Amazon Cognito" in architecture["nodes"]:
            node("cognito", "Amazon Cognito (인증 설계 필요)", "security", "aws")
            link("client", "cognito", "인증 토큰 취득", "authentication")
            link("cognito", "api", "JWT Authorizer 등 연결 제안", "policy")
        reviews.append({
            "id": "NET-SERVERLESS", "title": "Lambda VPC 및 성능 조건 미확정",
            "action": "DynamoDB/API Gateway 사용만으로 Lambda VPC 연결을 가정하지 마세요. 실행시간·피크 RPS·쿼터·콜드스타트 등을 검증하세요.",
        })
    elif option == "containers":
        # ALB는 최소 두 AZ의 public subnets에 연계해야 합니다.
        node("vpc", "VPC (CIDR 미확정)", "vpc", "aws")
        node("alb", "Public ALB · 2 AZ subnet 연계", "network", "vpc")
        link("client", "alb", "HTTPS 443 (ACM 인증서·WAF 정책 미확정)")
        for az in ("a", "b"):
            upper = az.upper()
            node("az_" + az, "논리 AZ-" + upper + " (실제 AZ ID 아님)", "az", "vpc")
            node("public_" + az, "Public Subnet " + upper, "subnet_public", "az_" + az)
            node("app_" + az, "Private App Subnet " + upper, "subnet_private", "az_" + az)
            link("alb", "public_" + az, "ALB의 public subnet 배치", "placement")
            link("public_" + az, "app_" + az, "ALB → ECS 트래픽 경계 (실제 SG/라우트 별도 확인)", "trust_boundary")
        # 운영 가용성 요구가 없으면 ECS 다중 AZ의 task 복제를 확정하지 않습니다.
        selected = ("a", "b") if ha else ("a",)
        for az in selected:
            node("task_" + az, "ECS Fargate 작업 " + az.upper(), "compute", "app_" + az,
                 refs=[req_refs.get("operations_preference")])
            link("alb", "task_" + az, "ALB 대상그룹 → 컨테이너 앱 포트 확인 필요",
                 refs=observed_refs[:2])
            link("task_" + az, "observability", "CloudWatch Logs/지표 설계", "telemetry")
        if db:
            node("db_subnet_group", "DB Subnet Group (2 AZ 필수)", "database_group", "vpc",
                 refs=[req_refs.get("requires_relational_database")])
            for az in ("a", "b"):
                node("db_" + az, "Private DB Subnet " + az.upper(), "subnet_database", "az_" + az)
                link("db_subnet_group", "db_" + az, "DB 서브넷 그룹 구성", "placement")
            node("rds", "Amazon RDS Primary (엔진/백업 확인)", "database", "db_a",
                 refs=[req_refs.get("requires_relational_database")])
            link("db_subnet_group", "rds", "DB 인스턴스가 서브넷 그룹 사용", "placement")
            for az in selected:
                link("task_" + az, "rds", "Private SG: 앱 → DB 포트 미확정",
                     refs=[req_refs.get("requires_relational_database")])
            if ha:
                node("rds_standby", "RDS Multi-AZ Standby (읽기 트래픽 없음)", "database", "db_b")
                link("rds", "rds_standby", "자동 장애 복구용 standby 복제 제안", "replication")
            else:
                reviews.append({
                    "id": "NET-RDS-SINGLE", "title": "단일 DB 실행 시 장애 대비 필요",
                    "action": "단일 AZ RDS에서 Multi-AZ 전환 여부와 RTO/RPO 및 비용을 확인하세요.",
                })
        reviews.extend([
            {
                "id": "NET-PRIVATE-EGRESS", "title": "Private ECS 외부 통신 경로 미설계",
                "action": "ECR 이미지 Pull, 로그·시크릿, 외부 API 통신에 NAT Gateway 또는 필요한 VPC Endpoint/Route Table을 선택하고 비용과 AZ 장애 영향을 검토하세요.",
            },
            {
                "id": "NET-ACL-IAM", "title": "ALB/Task/RDS의 실제 네트워크·권한 정책 미검증",
                "action": "Security Group 인바운드/아웃바운드, IAM 역할, TLS 및 Private IP 접근을 구축 전 검증하세요.",
            },
        ])
        if ha:
            reviews.append({
                "id": "NET-HA-ASSUMPTION", "title": "다중 AZ 토폴로지는 제안일 뿐",
                "action": "실제 리전의 AZ 지원, 최소 ECS task 수 2 이상, RDS Multi-AZ 설정과 비용·복구 검증을 확정하세요.",
            })
    else:
        raise ValueError("지원하지 않는 AWS 토폴로지 패턴입니다.")

    if contract.get("status") == "partial":
        reviews.append({
            "id": "NET-EVIDENCE-PARTIAL", "title": "코드 분석이 완료되지 않음",
            "action": "분석 실패 파일과 미지원 구문을 확인하고 API/DB 구조 오탐 가능성을 검토하세요.",
        })
    if "peak_rps" not in requirements:
        reviews.append({
            "id": "NET-TRAFFIC", "title": "피크 트래픽 미확인",
            "action": "피크 RPS·동시 연결·지연 목표를 입력한 뒤 스케일링 및 용량을 산정하세요.",
        })
    # 노드와 선의 유효한 참조, 가정 ID를 단계별 검증합니다.
    for n in nodes.values():
        if n["parent"] is not None and n["parent"] not in nodes:
            raise ValueError("토폴로지의 소속 영역을 찾지 못했습니다.")
    return {
        "schema_version": "1.0",
        "status": "proposed_unverified",
        "pattern": option,
        "region": region, "region_confirmed": bool(region and "region" in req_refs),
        "symbolic_azs": ["AZ-A", "AZ-B"] if option == "containers" else [],
        "high_availability_proposed": bool(ha and option == "containers"),
        "nodes": list(nodes.values()), "edges": links,
        "review_required": reviews,
        "assumptions": [
            "모든 AWS 서비스/서브넷/AZ는 설계 후보이며 실제 계정에서 조회한 자원이 아닙니다.",
            "AZ-A/B는 상징적 표기이며 실제 AZ 이름·ID를 지정하지 않습니다.",
            "CIDR, 보안그룹 세부 포트, NAT/VPC Endpoint, IAM 및 요금은 미확정입니다.",
            "기존 서비스 아이콘 참조도는 유지하며 상세 To-Be 토폴로지를 별도 산출물로 생성합니다.",
        ],
        "counts": {"nodes":len(nodes), "edges":len(links)},
    }


def markdown_topology(topology):
    out = ["# AWS 상세 네트워크·서비스 토폴로지 (참조 설계)", "",
           "> 상태: 제안/미검증. 실제 AWS 인프라·CIDR·IAM·RDS 장애 복구·요금이 확인된 설계가 아닙니다.",
           "", "- 참조 패턴: " + topology["pattern"],
           "- 리전: " + (topology["region"] or "사용자 확인 필요"),
           "- 고가용성 제안: " + ("2-AZ" if topology["high_availability_proposed"] else "미확정 또는 기본 배치"),
           "- 서비스/영역 노드: " + str(topology["counts"]["nodes"]), "",
           "## 설계 구성요소", "",
           "| 구성요소 | 유형 | 배치 영역 | 근거/제안 |",
           "| --- | --- | --- | --- |"]
    for node in topology["nodes"]:
        out.append("| " + node["name"] + " | " + node["kind"] + " | " +
                   (node["parent"] or "전역") + " | " +
                   (", ".join(node["evidence_ids"]) or "조건부 설계 제안") + " |")
    out += ["", "## 연결 및 트래픽 흐름", ""]
    for edge in topology["edges"]:
        out.append("- " + edge["source"] + " → " + edge["target"] +
                   " / " + edge["purpose"] + " (" + edge["kind"] + ")")
    out += ["", "## 구축 전 확인해야 할 사항", ""]
    out.extend("- [" + x["id"] + "] " + x["title"] + ": " + x["action"]
               for x in topology["review_required"])
    out += ["", "## 설계상 한계", ""]
    out.extend("- " + x for x in topology["assumptions"])
    return "\n".join(out) + "\n"
