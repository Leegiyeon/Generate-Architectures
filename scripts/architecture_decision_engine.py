"""AWS 실행 패턴의 선택/제외 근거를 정적 증거와 사용자 요구로만 비교합니다.

점수, 비용 순위, 성능 검증을 생성하지 않습니다.
EC2는 현재 참조 다이어그램에 없으므로 '검토 후보'일 뿐 자동 변경 대상이 아닙니다.
"""
CANDIDATES = (
    ("static", "S3 + CloudFront 정적 호스팅",
     ("CloudFront", "S3", "OAC"),
     "정적 자산 전달에 적합하나 API/SSR/상태 저장은 별도 실행 계층 필요"),
    ("lambda", "API Gateway + Lambda",
     ("API Gateway", "AWS Lambda", "선택 데이터 저장소"),
     "관리형 요청 기반 실행. 실행시간/동시성, DB 연결·콜드스타트 검토"),
    ("fargate", "ALB + ECS Fargate",
     ("Application Load Balancer", "Amazon ECS Fargate", "선택 RDS"),
     "컨테이너 기반 장기 API, VPC/Private outbound/운영·AZ 비용 검토"),
    ("ec2", "ALB + Amazon EC2",
     ("Application Load Balancer", "Amazon EC2", "선택 RDS"),
     "호스트 접근과 레거시 실행 가능하지만 OS/패치/스케일링 운영 책임 증가"),
    ("mobile_api", "모바일 백엔드 (Cognito/API Gateway/Lambda)",
     ("Cognito 선택", "API Gateway", "AWS Lambda"),
     "모바일 인증·백엔드용 참조안이며 모바일 앱 자체의 AWS 배포가 아님"),
)
CURRENT = {"static": "static", "serverless": "lambda",
           "containers": "fargate", "mobile": "mobile_api"}

DOCS = {
    "lambda_timeout": "https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html",
    "ecs_capacity": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-configuration.html",
    "alb": "https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-application-load-balancer.html",
}


def compare_architectures(architecture, profile, requirements, contract, topology=None,
                          data_review=None):
    selected = CURRENT.get(architecture["option_id"])
    if selected is None:
        raise ValueError("알 수 없는 AWS 참조 패턴 선택")
    req_ref = {r["key"]: r["id"] for r in contract["user_requirements"]}
    observed = [r["id"] for r in contract["observations"]]
    signal_ref = {r["signal"]: r["id"] for r in contract["configuration_inferences"]}
    signals = profile["signals"]
    workload = architecture.get("workload", "backend")
    has_api = signals.get("api_routes") is True
    relational = (requirements.get("requires_relational_database") is True or
                  (requirements.get("requires_relational_database") is not False and
                   signals.get("relational_database") is True))
    document = signals.get("document_database") is True
    needs_db = relational or document or requirements.get("requires_persistent_storage") is True
    host = requirements.get("requires_host_control") is True
    duration = requirements.get("max_job_duration_seconds")
    rendering = requirements.get("rendering_mode")
    can_static = profile.get("static_candidate", False)
    min_ops = requirements.get("operations_preference") == "minimize_maintenance"
    access_pattern = (data_review or {}).get("data_access_pattern", "undecided")

    items=[]
    for ident, title, services, tradeoff in CANDIDATES:
        hard=[]
        checks=[]
        evidence=[]
        rationale=[]
        def refuse(rule, reason, keys=()):
            hard.append({"rule_id":rule, "reason":reason,
                         "evidence_ids":[req_ref[k] for k in keys if k in req_ref]})
        def review(rule, reason, keys=()):
            checks.append({"rule_id":rule, "reason":reason,
                           "evidence_ids":[req_ref[k] for k in keys if k in req_ref]})
        def why(msg, ids=()):
            rationale.append(msg)
            evidence.extend(ids)
        if ident == "static":
            if workload == "mobile":
                refuse("DEC-STATIC-MOBILE", "모바일 클라이언트 백엔드의 단독 정적 호스팅을 대체하지 못합니다.")
            if has_api:
                refuse("DEC-STATIC-API", "코드에서 서버 API 경로가 확인되어 정적 단독 배포가 맞지 않습니다.")
                evidence += observed[:3]
            if needs_db:
                refuse("DEC-STATIC-DB", "영속 데이터 처리 계층이 필요한데 정적 단독 서비스에는 실행 계층이 없습니다.",
                       ("requires_persistent_storage", "requires_relational_database"))
            if rendering in ("ssr", "hybrid"):
                refuse("DEC-STATIC-SSR", "사용자가 SSR/서버 액션이 필요하다고 명시했습니다.", ("rendering_mode",))
            elif signals.get("nextjs") and not signals.get("next_static_export"):
                review("DEC-STATIC-UNPROVEN", "Next.js export 설정이 확인되지 않아 SSR이 없다는 증거가 없습니다.")
            if not can_static and not hard:
                review("DEC-STATIC-UNPROVEN", "정적 빌드 산출물과 브라우저 단독 동작을 확인해야 합니다.")
            if can_static:
                why("정적 웹 후보 파일/설정 단서가 있어 정적 호스팅을 비교할 수 있습니다.",
                    [signal_ref.get("next_static_export")] if signal_ref.get("next_static_export") else [])
            else:
                review("DEC-STATIC-BUILD", "서버 빌드/정적 export 실행 검증을 수행하지 않았습니다.")
        elif ident == "lambda":
            if host:
                refuse("DEC-LAMBDA-HOST", "OS/호스트 제어가 필요한 프로세스를 표준 Lambda 실행 계층으로 배포할 수 없습니다.",
                       ("requires_host_control",))
            if duration is not None and duration > 900:
                refuse("DEC-LAMBDA-DURATION",
                       "표준 Lambda 함수의 일반 구성 제한 900초를 초과합니다. 일부 특수 실행 방식은 별도 검토해야 합니다.",
                       ("max_job_duration_seconds",))
            if relational:
                refuse("DEC-LAMBDA-RDS-TEMPLATE",
                       "현재 Lambda 참조 템플릿에 RDS 네트워크·연결 풀이 없습니다. Lambda+RDS 별도 설계는 가능할 수 있습니다.",
                       ("requires_relational_database",))
            if document:
                review("DEC-LAMBDA-DOCDB", "MongoDB 의존성이 있지만 DynamoDB로 자동 변경할 수 없습니다.")
            if not has_api and workload != "mobile":
                review("DEC-LAMBDA-API-UNKNOWN", "API/이벤트 호출 및 함수 분리 가능 여부는 확인되지 않았습니다.")
            if duration is None:
                review("DEC-LAMBDA-DURATION-UNKNOWN", "호출 또는 작업의 최대 실행 시간을 확인해야 합니다.")
            why("요청/이벤트 단위로 서버 관리 부담을 줄이는 실행 계층을 검토합니다.")
        elif ident == "fargate":
            if host:
                refuse("DEC-FARGATE-HOST", "호스트 OS/커널 기능 직접 제어가 필요해 Fargate 제약과 충돌합니다.",
                       ("requires_host_control",))
            if signals.get("docker"):
                why("컨테이너 설정 단서가 발견되어 기존 패키징 방식 재사용을 검토합니다.",
                    [signal_ref["docker"]] if "docker" in signal_ref else [])
            else:
                review("DEC-FARGATE-PACKAGING", "컨테이너 이미지/빌드/헬스체크 구성이 확인되지 않았습니다.")
            if workload == "mobile":
                review("DEC-FARGATE-MOBILE", "모바일 클라이언트에서 사용할 서버 API가 필요한지 확인해야 합니다.")
            why("ALB와 ECS 작업을 분리해 웹/API 서버의 지속적인 실행을 검토합니다.")
            if topology and topology.get("pattern") == "containers" and topology.get("status") == "blocked_for_review":
                review("DEC-FARGATE-NETWORK", "선택한 NAT/Endpoint 또는 정적 제약에 충돌이 있습니다.")
        elif ident == "ec2":
            why("호스트 구성 및 OS 직접 관리가 필요한 경우에 비교할 후보입니다.",
                [req_ref["requires_host_control"]] if host and "requires_host_control" in req_ref else [])
            if not host:
                review("DEC-EC2-HOST", "직접 OS 제어 필요성 없이 EC2를 선택할 운영상 이점을 확인해야 합니다.")
            if min_ops:
                review("DEC-EC2-OPERATIONS", "서버 패치·AMI·접근통제·Auto Scaling 책임이 최소 관리 요구와 충돌할 수 있습니다.",
                       ("operations_preference",))
            review("DEC-EC2-TOPOLOGY", "EC2 상세 네트워크 설계는 현재 자동 참조 다이어그램으로 제공하지 않습니다.")
        elif ident == "mobile_api":
            if workload != "mobile":
                refuse("DEC-MOBILE-SCOPE", "모바일 클라이언트에 대한 명시적 요구 또는 기술 단서가 없습니다.")
            if relational:
                refuse("DEC-MOBILE-RDS-TEMPLATE",
                       "현 모바일 참조 템플릿은 관계형 DB 연결 구성을 제공하지 않습니다.",
                       ("requires_relational_database",))
            if host:
                refuse("DEC-MOBILE-HOST", "Lambda 기반 모바일 템플릿으로 호스트 제어 요구를 만족할 수 없습니다.",
                       ("requires_host_control",))
            if workload == "mobile":
                why("모바일 클라이언트의 인증·백엔드 API 후보를 검토합니다.",
                    [signal_ref["mobile"]] if "mobile" in signal_ref else [])
        # 데이터 접근 패턴은 DB 선택 증거가 아닙니다. 현재 참조 패턴이 미지원인 경우 검토를 요구합니다.
        if access_pattern == "document_queries" and ident in ("lambda", "mobile_api"):
            review("DEC-DOCSTORE-MODEL", "문서형 DB 조회를 DynamoDB에 그대로 적용할 수 없습니다. 기존 쿼리와 호환성을 검토하세요.",
                   ("data_access_pattern",))
        if access_pattern == "relational_transactions" and ident == "static":
            refuse("DEC-STATIC-TRANSACTIONS", "관계형 트랜잭션을 처리할 실행·DB 계층이 정적 웹 템플릿에 없습니다.",
                   ("data_access_pattern",))
        if access_pattern == "relational_transactions" and ident in ("lambda", "mobile_api"):
            refuse("DEC-RDB-TEMPLATE", "관계형 트랜잭션 요구가 있으나 현재 참조 템플릿은 관계형 DB를 연결하지 않습니다.",
                   ("data_access_pattern",))
        if access_pattern == "key_value" and ident == "ec2":
            review("DEC-EC2-KEYVALUE", "키 조회 업무만으로 OS 관리가 필요한 EC2를 선택할 근거는 확인되지 않았습니다.")
        # 정확한 사용자 트래픽을 받더라도 실측 용량 없이 적합 판정을 하지 않습니다.
        if requirements.get("peak_rps") is not None:
            review("DEC-CAPACITY-UNMEASURED",
                   "피크 RPS가 입력되었지만 서비스별 처리량/쿼터와 부하 테스트 결과가 없습니다.",
                   ("peak_rps",))
        if requirements.get("monthly_budget_usd") is not None:
            review("DEC-COST-UNVERIFIED",
                   "예산이 입력되었지만 후보별 SKU 요금/사용량으로 비용 우열을 검증하지 않았습니다.",
                   ("monthly_budget_usd",))
        if contract.get("status") == "partial":
            review("DEC-EVIDENCE-PARTIAL", "코드 분석 일부가 실패하여 후보 검토에 누락 가능성이 있습니다.")
        status = "blocked_for_current_template" if hard else "review_required"
        items.append({
            "id":ident, "title":title, "aws_services":list(services),
            "is_current_reference":ident==selected,
            "status":status, "blockers":hard, "review_required":checks,
            "rationale":rationale, "tradeoffs":[tradeoff],
            "evidence_ids":list(dict.fromkeys([i for i in evidence if i])),
            "cost_status":"not_estimated", "performance_status":"not_tested",
            "approved":False,
        })

    selected_item = next(x for x in items if x["id"] == selected)
    # 자동 전환이 아닌 사람이 검토할 수 있는 2개의 대안만 노출.
    alternates = [x["id"] for x in items if x["id"] != selected and
                  x["status"] != "blocked_for_current_template"][:2]
    return {
        "schema_version":"1.0",
        "status": ("blocked_for_review" if selected_item["blockers"] else
                   "alternatives_need_review"),
        "selected_reference":selected,
        "selected_reference_approved":False,
        "selected_reference_unchanged_by_ai":True,
        "candidates":items, "alternative_candidates":alternates,
        "user_approval_required":True, "production_ready":False,
        "references":DOCS,
        "limitations":[
            "이 표는 기존 참조 템플릿 비교이며 AWS 서비스 자체의 사용 불가 판정이 아닙니다.",
            "EC2 상세 To-Be 다이어그램과 신규 패턴 자동 선정 기능은 아직 제공하지 않습니다.",
            "성능·월간 총비용·실제 AWS 계정/보안 검증으로 후보 간 우열을 확정하지 않습니다.",
            "AI 검토 내용은 선택 결과를 자동 수정하지 않습니다.",
        ],
    }


def markdown_decision_matrix(result):
    rows = ["# AWS 배포 패턴 선정 근거 및 대안 비교", "",
            "> **검토용 참조안 / 최종 승인 전**. 성능·비용·보안·가용성을 실측하지 않았습니다.",
            "", "- 현재 참조 패턴: " + result["selected_reference"],
            "- 추천 게이트: " + result["status"],
            "- 대안 검토: " + ", ".join(result["alternative_candidates"]),
            "- 사람 승인 필요: 예", "",
            "| 후보 | 분류 | 거절/검토 필요 이유 | 운영 고려사항 |",
            "| --- | --- | --- | --- |"]
    for candidate in result["candidates"]:
        hard = "; ".join(x["reason"] for x in candidate["blockers"])
        unknown = "; ".join(x["reason"] for x in candidate["review_required"][:3])
        why = hard or unknown or "실제 서비스 구성과 요구사항 확인 필요"
        rows.append("| " + candidate["title"] +
                    (" **(현재 참조)**" if candidate["is_current_reference"] else "") +
                    " | " + candidate["status"] + " | " +
                    why.replace("|", "/") + " | " +
                    "; ".join(candidate["tradeoffs"]).replace("|", "/") + " |")
    rows += ["", "## 현재 참조 패턴의 선정/제외 이유", ""]
    for c in result["candidates"]:
        if not c["is_current_reference"]:
            continue
        rows.extend("- " + line for line in c["rationale"])
        rows.extend("- [" + x["rule_id"] + "] " + x["reason"] for x in c["blockers"])
        rows.extend("- [" + x["rule_id"] + "] " + x["reason"] for x in c["review_required"])
    rows += ["", "## 미검증 범위와 승인 절차", ""]
    rows.extend("- " + line for line in result["limitations"])
    rows += ["", "실제 채택은 운영 요구, 비용, AWS 실제 계정의 보안 및 부하 테스트를 확인한 뒤 결정합니다.", ""]
    return "\n".join(rows)



def build_decision_record(architecture, validation, decision_matrix,
                          data_review, contract):
    """ADR은 '제안'과 '사용자 승인'을 분리하며 기본 요구값을 사용자 입력으로 오해하지 않음."""
    user_input = [
        {"key": item["key"], "value": item["value"], "evidence_id": item["id"]}
        for item in contract["user_requirements"]
    ]
    selected = next(
        item for item in decision_matrix["candidates"]
        if item["is_current_reference"]
    )
    return {
        "schema_version": "1.0", "id": "ADR-0001",
        "status": "proposed_pending_human_approval",
        "chosen_reference": architecture["option_id"],
        "chosen_reference_detail": selected["id"],
        "automatic_deployment_allowed": False,
        "approval": {"required": True, "approved": False,
                     "approved_by": None, "approved_at": None},
        "observed_code_evidence_ids": [
            x["id"] for x in contract["observations"][:20]],
        "explicit_user_requirements": user_input,
        "unconfirmed_defaults": list(contract["system_defaults"]),
        "selection_rationale": list(selected["rationale"]),
        "constraints": list(selected["blockers"]),
        "unconfirmed_conditions": list(selected["review_required"]),
        "considered_alternatives": [
            {"id": option["id"], "status": option["status"],
             "rejection_reasons": option["blockers"],
             "tradeoffs": option["tradeoffs"]}
            for option in decision_matrix["candidates"] if not option["is_current_reference"]
        ],
        "data_access": {
            "pattern": data_review["data_access_pattern"],
            "source": data_review["pattern_source"],
            "selected_data_store": None,
            "migration_approved_for_automatic_change": False,
            "review_required": list(data_review["review_required"]),
        },
        "gate": {
            "architecture": validation["decision_gate"],
            "candidate_selection": decision_matrix["status"],
            "production_ready": False,
        },
        "future_approval_requirements": [
            "사용자 명시 요구와 참조 패턴의 충돌 해결",
            "DB 스키마·쿼리·데이터 전환 전략 확인 및 별도 승인",
            "네트워크 보안·가용성·트래픽/부하·운영 비용 검증",
            "AWS 리소스 자동 변경/배포는 본 제품에서 수행하지 않음",
        ],
    }


def markdown_decision_record(record):
    lines = [
        "# ADR-0001: AWS 참조 설계 결정 기록", "",
        "> **승인 전 / 실제 배포 아님**. AI 제안도 자동 반영하지 않습니다.",
        "", "- 상태: " + record["status"],
        "- 현재 참조 패턴: " + record["chosen_reference"],
        "- 대안 비교: " + record["chosen_reference_detail"],
        "- 검토 게이트: " + record["gate"]["architecture"], "",
        "## 1. 사용자가 명시한 요구사항", "",
    ]
    for item in record["explicit_user_requirements"]:
        lines.append("- " + item["evidence_id"] + " " + item["key"] +
                     ": " + str(item["value"]))
    if not record["explicit_user_requirements"]:
        lines.append("- 명시적 입력 없음. 아래 기본값은 사용자가 승인한 값이 아닙니다.")
    lines += ["", "## 2. 시스템 기본값 (사용자 승인 아님)", ""]
    for item in record["unconfirmed_defaults"]:
        lines.append("- " + item["key"] + ": " + str(item["value"]))
    lines += ["", "## 3. 선정 근거 / 코드 관찰 출처", ""]
    lines.extend("- " + x for x in record["selection_rationale"])
    lines.append("- 관찰 근거 ID: " +
                 (", ".join(record["observed_code_evidence_ids"]) or "미관찰"))
    lines += ["", "## 4. 배포 대안 선정·제외 이유", "",
              "| 후보 | 검토 상태 | 제외/추가 검토 근거 |",
              "| --- | --- | --- |"]
    for item in record["considered_alternatives"]:
        reason = "; ".join(x["reason"] for x in item["rejection_reasons"])
        if not reason:
            reason = "; ".join(item["tradeoffs"])
        lines.append("| " + item["id"] + " | " + item["status"] +
                     " | " + reason.replace("|", "/") + " |")
    lines += ["", "## 5. 저장소와 데이터 모델", "",
              "- 접근 패턴: " + record["data_access"]["pattern"],
              "- 출처: " + record["data_access"]["source"],
              "- 자동 마이그레이션: 사용하지 않음", "",
              "## 6. 승인 전 필수 조치", ""]
    for item in record["constraints"]:
        lines.append("- [차단 " + item["rule_id"] + "] " + item["reason"])
    lines.extend("- " + item for item in record["future_approval_requirements"])
    lines += ["", "실제 인프라 변경은 수행하지 않으며 사용자 승인은 별도 절차로 관리합니다.", ""]
    return "\n".join(lines)
