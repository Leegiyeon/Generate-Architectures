"""근거와 요구사항을 기반으로 AWS 참조 아키텍처 대안을 비교합니다.

LLM이 아닌 재현 가능한 규칙입니다. 점수, 실제 청구액 또는 적합성 보증을 생성하지 않습니다.
"""
from requirements_model import review_requirements


TEMPLATES = {
    "static": {
        "pattern": "정적 웹 배포 참조 아키텍처",
        "nodes": ["User", "Route 53", "CloudFront", "S3", "AWS WAF", "CloudWatch"],
        "edges": [("User", "Route 53"), ("Route 53", "CloudFront"),
                  ("CloudFront", "S3"), ("AWS WAF", "CloudFront"),
                  ("CloudFront", "CloudWatch")],
        "benefits": ["정적 파일 배포 구성을 단순화할 수 있습니다."],
        "tradeoffs": ["SSR·서버 액션·DB API가 있으면 별도 백엔드가 필요합니다."],
    },
    "serverless": {
        "pattern": "서버리스 API 참조 아키텍처",
        "nodes": ["Client", "API Gateway", "Lambda", "DynamoDB", "CloudWatch"],
        "edges": [("Client", "API Gateway"), ("API Gateway", "Lambda"),
                  ("Lambda", "DynamoDB"), ("Lambda", "CloudWatch")],
        "benefits": ["API 요청 기반으로 관리형 실행 환경을 검토할 수 있습니다."],
        "tradeoffs": ["실행시간·콜드스타트·DynamoDB 접근패턴을 별도로 검증해야 합니다."],
    },
    "containers": {
        "pattern": "컨테이너 기반 웹/API 참조 아키텍처",
        "nodes": ["User", "Route 53", "AWS WAF", "Application Load Balancer",
                  "ECS Fargate", "Amazon RDS", "CloudWatch"],
        "edges": [("User", "Route 53"), ("Route 53", "Application Load Balancer"),
                  ("AWS WAF", "Application Load Balancer"),
                  ("Application Load Balancer", "ECS Fargate"),
                  ("ECS Fargate", "Amazon RDS"), ("ECS Fargate", "CloudWatch")],
        "benefits": ["서버 실행과 관계형 데이터베이스가 필요한 애플리케이션을 검토할 수 있습니다."],
        "tradeoffs": ["VPC, 운영, 스케일링, RDS 비용과 백업 정책을 검증해야 합니다."],
    },
    "mobile": {
        "pattern": "모바일 애플리케이션 백엔드 참조 아키텍처",
        "nodes": ["Mobile App", "Amazon Cognito", "API Gateway", "Lambda",
                  "DynamoDB", "CloudWatch"],
        "edges": [("Mobile App", "Amazon Cognito"), ("Mobile App", "API Gateway"),
                  ("API Gateway", "Lambda"), ("Lambda", "DynamoDB"),
                  ("Lambda", "CloudWatch")],
        "benefits": ["모바일 인증 및 API 백엔드 구성의 출발점으로 활용할 수 있습니다."],
        "tradeoffs": ["기존 인증 제공자와 DB 모델에 따라 서비스가 달라질 수 있습니다."],
    },
}
PILLARS = {
    "운영 우수성": "배포·모니터링·사고 대응 절차를 운영환경에서 확인해야 합니다.",
    "보안": "IAM 최소 권한, 네트워크 통제, 암호화, 데이터 분류를 검사해야 합니다.",
    "안정성": "가용영역 장애, 백업, RTO/RPO, 장애 복구 테스트가 필요합니다.",
    "성능 효율성": "피크 요청량과 데이터 접근패턴을 기반으로 부하 테스트가 필요합니다.",
    "비용 최적화": "AWS 가격표·리전·실제 사용량을 이용한 산정이 필요합니다.",
    "지속 가능성": "실측 리소스 활용률과 불필요한 과잉 구성을 검토해야 합니다.",
}


def decide(profile, requirements):
    signals = profile["signals"]
    workload = requirements["workload"]
    if workload == "auto":
        categories = {m["category"] for m in profile["manifests"]}
        workload = "mobile" if signals["mobile"] else "web" if "web" in categories else "backend"

    relational = requirements.get("requires_relational_database", signals["relational_database"])
    preference = requirements["deployment_preference"]
    can_static = profile["static_candidate"] and not relational and workload == "web"
    feasible = {
        "static": can_static,
        "serverless": workload != "mobile" and not relational,
        "containers": workload != "mobile",
        "mobile": workload == "mobile",
    }
    # 정적 배포/서버리스의 전제 조건이 확인되지 않으면 안전한 비교용 초안을 우선합니다.
    if workload == "mobile":
        preferred = "mobile"
    elif signals["serverless_config"] and feasible["serverless"]:
        preferred = "serverless"
    elif signals["docker"] or relational or signals["nextjs"]:
        preferred = "containers"
    elif can_static:
        preferred = "static"
    elif workload == "backend":
        preferred = "serverless" if feasible["serverless"] else "containers"
    else:
        preferred = "containers"

    blockers = []
    if preference != "auto":
        if feasible.get(preference, False):
            preferred = preference
        else:
            blockers.append("요청한 " + preference + " 배포는 코드 근거 또는 데이터 요구와 충돌하여 자동 선택하지 않았습니다.")
    if preferred not in TEMPLATES:
        raise ValueError("지원하지 않는 배포 유형입니다.")
    if signals["nextjs"] and not signals["next_static_export"]:
        blockers.append("Next.js의 SSR/서버 액션 사용 여부를 확인할 때까지 정적 배포를 확정할 수 없습니다.")
    if relational and preferred == "containers":
        blockers.append("RDS는 후보 서비스일 뿐입니다. 기존 관계형 DB 사용 여부와 실제 엔진을 확인해야 합니다.")
    if not profile["manifests"]:
        blockers.append("분석 가능한 기술 설정 파일이 없어 아키텍처 추천의 근거가 부족합니다.")
    if profile["scan_truncated"]:
        blockers.append("저장소 파일 검색이 상한에 도달해 일부 파일을 검사하지 못했습니다.")

    options = []
    for name in ("static", "serverless", "containers", "mobile"):
        template = TEMPLATES[name]
        options.append({
            "id": name, "name": template["pattern"],
            "applicable": feasible[name],
            "selected": name == preferred,
            "advantages": template["benefits"],
            "tradeoffs": template["tradeoffs"],
            "cost_status": "미산정: 실제 리전·사용량·가격표가 필요합니다.",
        })
    selected = TEMPLATES[preferred]
    questions = list(dict.fromkeys(profile["questions"] + review_requirements(requirements)))
    if not signals["api_routes"] and workload in ("web", "backend"):
        questions.append("실제 API 서버, 백그라운드 작업 또는 서버 측 렌더링이 있나요?")
    if requirements.get("environment") == "production":
        questions.append("상용 배포 전 보안 검토·부하 테스트·장애 복구 훈련 담당자는 누구인가요?")
    return {
        "workload": workload,
        "pattern": selected["pattern"],
        "option_id": preferred,
        "input_budget_usd_month": requirements.get("monthly_budget_usd"),
        "detected_technologies": profile["technologies"],
        "evidence": profile["manifests"],
        "nodes": selected["nodes"], "edges": selected["edges"],
        "requirements": requirements,
        "repository_analysis": profile,
        "decision": {
            "status": "검토용 초안",
            "rationale": [
                "파일 경로 및 알려진 의존성에 근거한 규칙 기반 참조 설계입니다.",
                "현재 선택: " + selected["pattern"],
                "실제 가용성, 비용 및 보안은 확인하지 않았습니다.",
            ],
            "warnings": blockers, "alternatives": options,
        },
        "questions": questions,
        "well_architected_review": [
            {"pillar": name, "status": "검증 전", "required_check": check}
            for name, check in PILLARS.items()
        ],
        "limitations": profile["limitations"] + [
            "리소스가 실제 AWS에 배포되었거나 구축 가능함을 보증하지 않습니다.",
            "비용 예측, 부하 테스트, 정책 검사, IaC 생성은 아직 제공하지 않습니다.",
        ],
    }


def markdown_report(result):
    profile = result["repository_analysis"]
    decision = result["decision"]
    esc = lambda value: str(value).replace("|", "/").replace("\n", " ").replace("`", "'")
    lines = [
        "# AWS 솔루션 아키텍처 검토 보고서",
        "",
        "> **상태: 검토용 초안.** 실제 AWS 인프라를 조회하거나 배포하지 않았습니다.",
        "",
        "## 1. 분석 요약",
        "",
        "- 추천 기준 패턴: **" + esc(result["pattern"]) + "**",
        "- 워크로드: " + result["workload"],
        "- 발견된 기술: " + (", ".join(profile["technologies"]) or "검출되지 않음"),
        "- 월 예산 입력: " + (str(result["input_budget_usd_month"]) + " USD" if result["input_budget_usd_month"] is not None else "미입력") + " (비용 추정 아님)",
        "- 검사 파일 수: " + str(profile["inspected_files"]),
        "",
        "## 2. 확인된 근거 (추정과 구분)",
        "",
    ]
    lines.extend("- `" + esc(e["path"]) + "` → " + esc(e["technology"])
                 for e in result["evidence"])
    if not result["evidence"]:
        lines.append("- 지원하는 설정 파일을 발견하지 못했습니다.")
    lines += [
        "",
        "## 3. 아키텍처 대안 비교",
        "",
        "| 대안 | 검토 가능 여부 | 장점 | 주의점 |",
        "| --- | --- | --- | --- |",
    ]
    for option in decision["alternatives"]:
        lines.append("| " + esc(option["name"]) + (" **(선택)**" if option["selected"] else "") +
                     " | " + ("가능" if option["applicable"] else "현재 근거상 부적합") + " | " +
                     esc(" ".join(option["advantages"])) + " | " +
                     esc(" ".join(option["tradeoffs"])) + " |")
    lines += ["", "## 4. 주요 위험·미확인 항목", ""]
    lines.extend("- " + warning for warning in decision["warnings"])
    if not decision["warnings"]:
        lines.append("- 명시적으로 차단된 패턴은 없지만, 아직 검증 전입니다.")
    lines += ["", "## 5. AWS Well-Architected 검토 체크리스트", ""]
    for item in result["well_architected_review"]:
        lines.append("- **" + item["pillar"] + " (검증 전)**: " + item["required_check"])
    lines += ["", "## 6. 설계 확정 전 확인 질문", ""]
    lines.extend("- " + question for question in result["questions"])
    lines += [
        "", "## 7. 다이어그램과 제한사항", "",
        "- `architecture.svg`: AWS 서비스 아이콘이 내장된 SVG",
        "- `architecture.png`: 이미지",
        "- `architecture.dot`: Graphviz 원본",
        "- `architecture.json`: 구조화된 근거, 대안, 미확인 조건",
        "- `repository-analysis.json`: 프로젝트 분석 결과",
        "- `requirements-used.json`: 설계에 사용된 명시적 입력값",
        "",
    ]
    lines.extend("- " + limitation for limitation in result["limitations"])
    return "\n".join(lines) + "\n"
