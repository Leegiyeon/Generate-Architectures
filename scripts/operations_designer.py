"""AWS Architecture Designer의 보안·확장·복구·운영 청사진 (설계 제안만).

실제 클라우드 자원/IAM/운영 트래픽을 조회하거나 변경하지 않습니다.
불확실한 SLO, 경보 임계치, 예약 용량, 운영 비용은 수치로 지어내지 않습니다.
"""
PILLARS = {
    "operational_excellence": "운영 우수성",
    "security": "보안",
    "reliability": "안정성",
    "performance_efficiency": "성능 효율성",
    "cost_optimization": "비용 최적화",
    "sustainability": "지속 가능성",
}
REFERENCES = {
    "well_architected": "https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html",
    "ecs_scaling": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html",
    "ecs_target_tracking": "https://docs.aws.amazon.com/AmazonECS/latest/developerguide/target-tracking-create-policy.html",
    "lambda_metrics": "https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html",
    "lambda_concurrency": "https://docs.aws.amazon.com/lambda/latest/dg/monitoring-concurrency.html",
    "security_groups": "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html",
    "rds_backups": "https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html",
}


def design_operations(architecture, topology, requirements, contract,
                      decision_matrix=None, data_review=None):
    """선택한 To-Be 토폴로지에서 실제 존재하는 서비스만 대상으로 정책 후보를 만듭니다."""
    pattern = topology["pattern"]
    if pattern not in ("containers", "serverless", "mobile", "static"):
        raise ValueError("지원하지 않는 운영 설계 패턴입니다.")
    req_refs = {r["key"]: r["id"] for r in contract["user_requirements"]}
    nodes = {n["id"]: n for n in topology["nodes"]}
    edges = {(e["source"], e["target"]) for e in topology["edges"]}
    controls=[]
    alarms=[]
    questions=[]
    scaling=[]
    references_used = []
    def refs(*keys):
        return [req_refs[k] for k in keys if k in req_refs]
    def control(ident, pillar, title, goal, services=(), input_keys=(), verify="설정 확인/실측 필요"):
        selected = list(services)
        if any(x not in nodes for x in selected):
            raise ValueError("To-Be에 없는 서비스의 운영 통제: " + ident)
        controls.append({
            "id": ident, "pillar": pillar, "title": title,
            "proposal": goal, "topology_nodes": selected,
            "requirement_evidence_ids": refs(*input_keys),
            "status": "proposed_not_verified",
            "verification": verify,
            "approval_required": True,
        })
    def alarm(ident, scope, metric, intent, namespace, dimensions=None):
        if scope not in nodes:
            raise ValueError("관측 대상 AWS 서비스가 To-Be에 없음")
        alarms.append({
            "id":ident, "topology_node":scope, "metric":metric,
            "namespace":namespace, "dimension_design":dimensions,
            "purpose":intent,
            "threshold":None, "evaluation_periods":None,
            "alarm_action":None, "status":"proposal_needs_baseline",
            "reason":"실제 계정 지표/오류 예산·SLO가 확인되지 않아 임계값을 정하지 않음",
        })
    def question(ident, title, answer_key=None):
        if answer_key and answer_key in req_refs:
            return
        questions.append({"id":ident, "question":title, "status":"unconfirmed"})
    def scale(ident, node_id, metric, metric_namespace, objective, docs):
        if node_id not in nodes:
            raise ValueError("없는 컴퓨팅 서비스에 오토스케일러를 적용할 수 없음")
        scaling.append({
            "id":ident, "scope":node_id,
            "metric":metric, "metric_namespace":metric_namespace,
            "objective":objective,
            "min_capacity":None, "max_capacity":None,
            "target_value":None, "estimated_capacity":None,
            "quota_checked":False, "load_tested":False,
            "status":"candidate_requires_load_test",
            "reference":REFERENCES[docs],
        })
        references_used.append(docs)

    control("SEC-IAM-LEAST", "security", "IAM 최소 권한",
            "실행 역할과 운영 역할을 분리하고 실제 필요한 API 작업만 허용; 와일드카드 자원·작업 검토",
            ("observability",), verify="실제 IAM 역할·리소스/액션·SCP 및 교차 계정 권한 검증")
    control("OPS-LOGGING", "operational_excellence", "로그·추적·보관 정책",
            "애플리케이션 로그·요청 식별자·변경 감사 로그를 수집하고 보존기한/접근권한/민감정보 비식별화 확정",
            ("observability",), verify="CloudWatch 로그 수집 여부·필터·보존주기·실제 로그 유출 확인")
    control("SEC-SECRETS", "security", "비밀정보 및 키 관리",
            "환경변수 평문/소스 내 비밀키 보관을 금지하고 관리형 비밀 저장소 및 회전 정책 검토",
            (), verify="Secrets Manager/Parameter Store 선택, IAM·KMS·회전·소스코드 비밀 검사")
    control("OPS-ROLLBACK", "operational_excellence", "배포·롤백 운영",
            "배포 전후 건강 상태, 변경 승인·릴리스 이력, 실패 시 롤백과 복구 절차를 정의",
            (), verify="배포 파이프라인 및 롤백 리허설")
    control("REL-DR-PLAN", "reliability", "장애 대응·복구 계획",
            "장애 시나리오, 데이터/서비스 복원 순서, 운영자 연락망 및 복구 훈련",
            (), ("rto_minutes", "rpo_minutes"), "장애 주입/복구 훈련 및 백업 복원 시간 기록")
    control("COST-BUDGET", "cost_optimization", "비용 및 용량 감시",
            "로그/백업/NAT/데이터 전송과 리소스 크기에 대한 실제 청구 데이터·경보를 수립",
            (), ("monthly_budget_usd",), "AWS Pricing/Cost Explorer/청구서 및 사용량 검증")
    control("SUS-RESOURCE", "sustainability", "과잉 용량 검토",
            "실제 이용률과 부하 테스트를 바탕으로 과잉 리소스·불필요한 보관 데이터 감축",
            (), verify="실측 CPU·메모리·요청·스토리지 이용률 확보")
    if requirements.get("data_classification") == "sensitive":
        control("SEC-SENSITIVE", "security", "민감 데이터 보호",
                "전송·저장 암호화/KMS 키·최소 권한·데이터 보존과 삭제·감사 정책을 업무/규제 기준과 대조",
                (), ("data_classification",), "개인정보·규제 항목, 보존주기, 접근 로그, 키 정책 실증")
    if requirements.get("requires_authentication") is True:
        control("SEC-AUTH", "security", "사용자 인증·인가 검증",
                "사용자 로그인·토큰 검증·서버 측 권한/테넌트 분리 정책을 실제 API 권한과 대조",
                (), ("requires_authentication",), "권한 없는 호출/IDOR/만료된 토큰 등 테스트")
    if requirements.get("requires_authentication") is None:
        question("Q-AUTH", "로그인/사용자별 권한 통제 필요 여부를 확인하세요.",
                 "requires_authentication")
    if requirements.get("data_classification") in (None,"unknown"):
        question("Q-DATA", "처리 데이터의 민감도/암호화·보존 기한은 무엇인가요?",
                 "data_classification")

    if pattern == "containers":
        if not {"alb","task_a","app_a"}.issubset(nodes):
            raise ValueError("ECS 네트워크 참조안 필수 구조 불완전")
        task_nodes = [x for x in ("task_a", "task_b") if x in nodes]
        if topology.get("alb_scheme") == "internet_facing":
            control("SEC-PUBLIC-EDGE", "security", "공개 웹 경계",
                    "ALB HTTPS(ACM) 및 선택적 WAF/인바운드 정책을 정의; 백엔드·DB 직접 공개 금지",
                    ("alb","waf"), ("alb_scheme",), "ALB Scheme/Security Group/ACM/WAF·DNS 정책 실환경 확인")
        else:
            control("SEC-INTERNAL-EDGE", "security", "내부 전용 경계",
                    "Internal ALB 접근을 VPC/VPN/전용망에서만 허용하고 엔드포인트 공개 여부 검증",
                    ("alb",), ("alb_scheme",), "Internal ALB의 SG/라우트/VPN/DX/TGW 경로 확인")
        for task in task_nodes:
            if ("alb",task) not in edges:
                raise ValueError("ALB→ECS 연결이 없는 네트워크 설계와 운영 전략이 모순됨")
        sg = topology.get("network_controls", [])
        expected = {"SG-ALB-443"}
        expected.update("SG-APP-" + az.upper()
                        for az in ("a","b") if "task_" + az in nodes)
        if "rds" in nodes:
            expected.update("SG-DB-" + az.upper()
                            for az in ("a","b") if "task_" + az in nodes)
        if not expected.issubset({x["id"] for x in sg}):
            raise ValueError("네트워크 Security Group 접근 의도와 애플리케이션 경계 불일치")
        control("SEC-SG-CHAIN", "security", "최소 허용 SG 통신",
                "ALB SG→ECS SG→(필요 시) RDS SG의 포트만 허용. 비허용 CIDR/포트는 별도 확인",
                ("alb",)+tuple(task_nodes), ("container_port","database_port"),
                "실제 SG 규칙·대상 그룹/DB 포트와 접근권한 일치 검사")
        scale("SCALE-ECS-CPU", "task_a", "ECSServiceAverageCPUUtilization",
              "AWS/ECS", "CPU 활용량 기반 ECS Service Auto Scaling 후보", "ecs_target_tracking")
        scale("SCALE-ECS-MEM", "task_a", "ECSServiceAverageMemoryUtilization",
              "AWS/ECS", "메모리 기반 ECS 서비스 스케일 후보", "ecs_target_tracking")
        scale("SCALE-ECS-ALB", "task_a", "ALBRequestCountPerTarget",
              "AWS/ApplicationELB", "ALB 대상그룹 요청 기반 서비스 스케일 후보", "ecs_target_tracking")
        alarm("ALARM-ALB-5XX", "alb", "HTTPCode_Target_5XX_Count", "백엔드 5xx 오류 추적", "AWS/ApplicationELB")
        alarm("ALARM-ALB-LATENCY", "alb", "TargetResponseTime", "응답시간과 SLO 추적", "AWS/ApplicationELB")
        alarm("ALARM-ECS-CPU", "task_a", "CPUUtilization", "ECS CPU 과부하 감시", "AWS/ECS")
        control("OPS-ECS-DEPLOY", "operational_excellence", "ECS 배포 안전장치",
                "서비스 헬스체크·배포 회로 차단/롤백 및 태스크 정의 버전 관리 후보",
                ("alb","task_a"), verify="ECS 서비스 배포 컨트롤러/회로차단 설정·롤백 검증")
        if topology.get("high_availability_proposed"):
            if "task_b" not in nodes:
                raise ValueError("HA 요구와 다중 AZ ECS 태스크 토폴로지 충돌")
            control("REL-2AZ-ECS", "reliability", "ECS 다중 AZ 배치 제안",
                    "두 논리 AZ로 ECS 작업을 분산하도록 설계하되 가용성·최소 작업 수·스케일 정책은 승인 전",
                    ("task_a","task_b"), ("availability_target_percent","operations_preference"),
                    "AZ 배치·작업 수·ALB 헬스체크/장애 전환 및 부하 시험")
        else:
            question("Q-2AZ", "ECS 다중 AZ 작업 배치, 허용 장애시간과 가용성 목표를 확정하세요.")
        if "rds" in nodes:
            control("REL-RDS-BACKUP", "reliability", "RDS 백업·복원",
                    "자동 백업 보관 기간/PITR·스냅샷·암호화 및 복원 리허설을 별도로 설계",
                    ("rds",), ("rto_minutes","rpo_minutes"),
                    "백업 활성화/복원 성공·정합성·복원 소요시간 실측")
            alarm("ALARM-RDS-CONNECTIONS", "rds", "DatabaseConnections",
                  "DB 연결 수/풀·스케일 병목 분석", "AWS/RDS")
            alarm("ALARM-RDS-FREESTORAGE", "rds", "FreeStorageSpace",
                  "DB 저장 여유 공간 추적", "AWS/RDS")
            if "rds_standby" in nodes:
                control("REL-RDS-MULTIAZ", "reliability", "RDS Multi-AZ standby",
                        "Standby는 읽기 확장 노드가 아니며 장애 복구 전환·데이터 복제 상태를 확인",
                        ("rds","rds_standby"), verify="Multi-AZ RDS 설정과 Failover 복구 시간 테스트")
        if topology.get("egress_strategy") == "undecided":
            question("Q-EGRESS", "Private ECS에 필요한 ECR/로그/Secret/외부 API outbound NAT·Endpoint 전략을 결정하세요.")
        if any(x["id"] == "NET-EGRESS-CONFLICT" for x in topology["review_required"]):
            control("SEC-EGRESS-CONFLICT", "security", "외부 호출·VPC Endpoint 충돌",
                    "일반 인터넷 호출이 필수인데 AWS 서비스 Endpoint-only가 입력되어 배포 전 경로 재설계",
                    ("alb",), ("external_outbound_required","egress_strategy"),
                    "외부 API 요청 실경로 및 egress 정책 확인")
    elif pattern in ("serverless","mobile"):
        if not {"api","lambda"}.issubset(nodes):
            raise ValueError("서버리스 제안에서 API/Lambda가 누락됨")
        scale("SCALE-LAMBDA-CONCURRENCY","lambda","ConcurrentExecutions",
              "AWS/Lambda","동시 실행 및 Service Quotas 검토", "lambda_concurrency")
        alarm("ALARM-LAMBDA-ERROR", "lambda", "Errors", "함수 에러율/에러 건수 모니터링", "AWS/Lambda")
        alarm("ALARM-LAMBDA-DURATION", "lambda", "Duration", "지연/타임아웃 모니터링", "AWS/Lambda")
        alarm("ALARM-LAMBDA-THROTTLES", "lambda", "Throttles", "동시성/쿼터 초과 모니터링", "AWS/Lambda")
        control("SEC-API-AUTH", "security", "API Gateway 보안 정책",
                "사용자별 인가/메서드 접근 제어·요청 제한·WAF 필요 여부를 검토",
                ("api",), ("requires_authentication",), "실제 Authorizer·요청 인증·로그/WAF 설정")
        if "dynamodb" in nodes:
            control("REL-DDB-PITR", "reliability", "DynamoDB 데이터 보호",
                    "PITR/백업·테이블 접근제어·복원 실증을 검토",
                    ("dynamodb",), ("rpo_minutes","rto_minutes"),
                    "DynamoDB PITR/테이블 복원·IAM 및 용량 검증")
        question("Q-LAMBDA-QUOTA","Lambda 동시실행 쿼터, 함수 실행시간/비용, 외부 서비스 요청 제한을 검토하세요.")
    else:
        if not {"cdn","bucket"}.issubset(nodes):
            raise ValueError("정적 웹 제안 CloudFront/S3 누락")
        control("SEC-S3-OAC", "security", "CloudFront/S3 비공개 오리진",
                "S3 REST 오리진+OAC 정책, TLS 인증서 및 Public Access Block을 검토",
                ("cdn","bucket"), verify="S3 bucket policy/OAC/ACM/CloudFront 설정 확인")
        alarm("ALARM-CF-5XX", "cdn", "5xxErrorRate",
              "CDN 5xx 오류율 및 오리진 장애 알림 검토", "AWS/CloudFront")
        question("Q-STATIC-RELEASE", "정적 파일 배포의 캐시 무효화, 원본 버전·롤백 정책을 확정하세요.")

    # 공통 고객 입력과 실측 항목: 정확히 받은 값만 표시합니다.
    demand = {
        "average_rps": requirements.get("average_rps"),
        "peak_rps": requirements.get("peak_rps"),
        "peak_concurrent_connections": requirements.get("peak_concurrent_connections"),
        "latency_target_ms": requirements.get("latency_target_ms"),
        "availability_target_percent": requirements.get("availability_target_percent"),
        "rto_minutes": requirements.get("rto_minutes"),
        "rpo_minutes": requirements.get("rpo_minutes"),
        "environment": requirements.get("environment"),
        "budget_usd": requirements.get("monthly_budget_usd"),
        "input_provenance": {
            k: ("user_explicit" if k in req_refs else "system_default_or_missing")
            for k in ("average_rps","peak_rps","latency_target_ms",
                      "availability_target_percent","rto_minutes","rpo_minutes",
                      "environment","monthly_budget_usd")
        },
    }
    for key, msg in (
        ("peak_rps","최대 요청량(peak RPS)은 얼마인가요?"),
        ("latency_target_ms","목표 응답 지연(ms)을 입력해 주세요."),
        ("availability_target_percent","가용성 목표와 측정 방식을 정의해 주세요."),
        ("rto_minutes","서비스 복구 목표 RTO(분)는 얼마인가요?"),
        ("rpo_minutes","데이터 복구 목표 RPO(분)는 얼마인가요?"),
    ):
        question("Q-"+key.upper(),msg,key)
    if topology.get("status") == "blocked_for_review":
        question("Q-TOPOLOGY-BLOCK","네트워크·워크로드·DB 구성 충돌을 해결하기 전에는 배포 초안을 승인하지 마세요.")
    if decision_matrix and decision_matrix.get("status") == "blocked_for_review":
        question("Q-DECISION-BLOCK","현재 AWS 서비스 참조 템플릿의 명시적 적용 불가 조건을 먼저 해결하세요.")
    if contract.get("status") == "partial":
        question("Q-CODE-COVERAGE","분석 실패 파일/지원되지 않는 코드를 검토해 실제 배포 요건을 확인하세요.")

    # 실제 지표·쿼터가 검증되지 않아 항상 준비 미완료로 처리합니다.
    return {
        "schema_version":"1.0",
        "status":"proposal_requires_review",
        "scope":"aws_reference_design_static_operations_only",
        "selected_pattern":pattern,
        "topology_status":topology["status"],
        "account_checked":False,
        "security_verified":False, "slo_verified":False,
        "deployment_executed":False, "production_ready":False,
        "scaling":{"demand":demand, "policies":scaling,
                   "thresholds_estimated":False, "load_tested":False,
                   "service_quotas_checked":False},
        "security_and_operations":controls,
        "alerts":alarms,
        "recovery":{"rto_target_minutes":requirements.get("rto_minutes"),
                    "rpo_target_minutes":requirements.get("rpo_minutes"),
                    "restore_tested":False,"failover_tested":False,
                    "available_ha_nodes":[n for n in ("task_a","task_b","rds_standby")
                                          if n in nodes]},
        "questions":questions,
        "well_architected":[{"pillar_id":key,"name":name,
                             "status":"review_required",
                             "control_ids":[c["id"] for c in controls if c["pillar"]==key]}
                            for key,name in PILLARS.items()],
        "references":{name:REFERENCES[name] for name in sorted(set(references_used))},
        "limitations":[
            "다이어그램과 SG/Route 의도에서 확인되는 구성만 설계 대상으로 삼고 실제 설정을 생성하지 않습니다.",
            "트래픽이 입력되어도 CPU/RPS 임계값, 최소·최대 인스턴스 수, 운영 비용을 무근거로 결정하지 않습니다.",
            "AWS 계정·IAM 정책·TLS·백업·장애 복원과 실제 알람 설정을 검증하지 않습니다.",
            "SLA/SLO 충족, 보안 적합성, 장애 복구, 실제 비용은 운영 계정/부하/복구 시험 후 확인해야 합니다.",
        ],
    }


def markdown_operations(plan):
    lines = [
        "# AWS 보안·확장성·유지보수 설계 청사진", "",
        "> **제안/검증 전** — AWS IAM/SG/알람/Auto Scaling/백업 설정을 실행하거나 조회하지 않았습니다.",
        "", "- 참조 패턴: " + plan["selected_pattern"],
        "- AWS 계정 실사: 미수행",
        "- 운영 준비 판정: 미검증", "",
        "## 1. 요구사항 및 용량 근거", "",
        "| 입력 항목 | 값 | 출처 |", "| --- | --- | --- |",
    ]
    for field, value in plan["scaling"]["demand"].items():
        if field == "input_provenance":
            continue
        lines.append("| " + field + " | " +
                     (str(value) if value is not None else "미입력") + " | " +
                     plan["scaling"]["demand"]["input_provenance"].get(field,"요구사항") + " |")
    lines += ["", "## 2. 오토스케일링/용량/쿼터 제안", "",
              "| 대상 | 지표 | 타깃 임계값 | 상태 |", "| --- | --- | --- | --- |"]
    for rule in plan["scaling"]["policies"]:
        lines.append("| " + rule["scope"] + " | " + rule["metric"] +
                     " | 미정(실측 필요) | " + rule["status"] + " |")
    if not plan["scaling"]["policies"]:
        lines.append("| 정적 콘텐츠 | 캐시/오리진 요청 지표 추적 | 서비스별 검토 | 배포 전 |")
    lines += ["", "## 3. 접근통제·운영·백업·모니터링 설계", "",
              "| 원칙 | 서비스 | 항목 | 현 상태 |",
              "| --- | --- | --- | --- |"]
    for c in plan["security_and_operations"]:
        lines.append("| " + PILLARS[c["pillar"]] + " | " +
                     (", ".join(c["topology_nodes"]) or "공통 운영") + " | " +
                     c["title"] + " | " + c["status"] + " |")
        lines.append("> 확인: " + c["verification"])
    lines += ["", "## 4. 경보 제안 (임계값 미확정)", "",
              "| 서비스 | CloudWatch 지표 | 임계값 |",
              "| --- | --- | --- |"]
    for alarm in plan["alerts"]:
        lines.append("| " + alarm["topology_node"] + " | " + alarm["metric"] +
                     " | 미정(운영 기준선 필요) |")
    lines += ["", "## 5. 복구 및 운영 책임", "",
              "- 목표 RTO(분): " + str(plan["recovery"]["rto_target_minutes"]),
              "- 목표 RPO(분): " + str(plan["recovery"]["rpo_target_minutes"]),
              "- 실제 복원 시험: 미수행",
              "- 장애 전환 시험: 미수행", "",
              "## 6. 사용자 확인이 필요한 항목", ""]
    lines.extend("- " + item["question"] for item in plan["questions"])
    lines += ["", "## 7. AWS Well-Architected 관점", ""]
    lines.extend("- " + item["name"] + ": 검토 전 / 제안 항목 " +
                 ", ".join(item["control_ids"]) for item in plan["well_architected"])
    lines += ["", "## 8. 주의사항", ""]
    lines.extend("- " + item for item in plan["limitations"])
    lines += ["", "## 9. 공식 참고 문서", ""]
    lines.extend("- " + key + ": " + link for key, link in plan["references"].items())
    return "\n".join(lines) + "\n"
