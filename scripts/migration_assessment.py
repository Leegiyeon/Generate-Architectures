"""선언된 As-Is와 코드 단서에 기반한 보수적 AWS Migration Assessment 초안.

AWS 7 Rs 중 Rehost/Replatform만 1차 비교합니다. 관리형 서비스 호환, 이전 가능성,
데이터 이전/중단 시간, 비용, 인프라 수량은 검증 없이 확정하지 않습니다.
"""
from collections import Counter

SUPPORTED_RDS = {"postgresql", "mysql", "mariadb", "sqlserver", "oracle"}
RELATIONAL = SUPPORTED_RDS
REFERENCES = {
    "strategies": "https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html",
    "migration_discovery": "https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-portfolio-playbook/discovery.html",
}


def _change(server, component, decision, target, reason, index, evidence=None):
    """원본 서버 별칭을 코드 단서와 혼동하지 않는 결정 단위."""
    source_ref = "as-is-inventory.json#/servers/" + str(index)
    return {
        "server_id": server["id"], "component": component, "decision": decision,
        "to_be_candidate": target, "reason": reason,
        "evidence": [{"type": "user_declared_unverified", "ref": source_ref}] +
                    [{"type": "repository_code_signal", "ref": x} for x in (evidence or [])],
        "validated": False, "change_approved": False,
    }


def _risk(code, title, question, evidence, severity="review_required", strategies=None):
    return {"id": code, "title": title, "severity": severity,
            "question": question, "evidence": evidence,
            "applies_to": strategies or ["rehost", "replatform"],
            "verified": False}


def _rehost(server, index):
    role, os_name, db = server["role"], server["os"], server["db_engine"]
    if role == "unknown" or os_name == "unknown":
        return [_change(server, "server", "unknown",
                        "Amazon EC2 (OS·역할 확인 후 검토)",
                        "운영체제 또는 서버 역할이 미확정이므로 Rehost 가능성을 판단할 수 없습니다.", index)]
    note = ("현재 OS·미들웨어·데이터 및 의존성 유지 검토. "
            "EC2 인스턴스 크기/라이선스·지원 OS·스토리지/네트워크 검증 전.")
    if db not in ("none", "unknown"):
        note += " DB 엔진/버전·일관성·백업/복구·데이터 이전 경로도 별도 검증."
    return [_change(server, "server", "relocate", "Amazon EC2 (원형 유지 후보)", note, index)]


def _replatform(server, index, profile):
    role, os_name, db = server["role"], server["os"], server["db_engine"]
    changes = []
    app_like = role in ("application", "mixed", "proxy")
    if role in ("application", "mixed"):
        if os_name == "windows":
            changes.append(_change(
                server, "application", "unknown", "EC2 유지 또는 ECS 검토",
                "Windows 이미지/런타임·라이선스와 ECS 실행 지원을 확인하지 않아 Fargate 이전을 추천하지 않습니다.", index))
        elif os_name == "unknown":
            changes.append(_change(
                server, "application", "unknown", "앱 런타임 확인 전 목표 서비스 미정",
                "OS·앱 실행 방식이 불명확해 컨테이너 지원을 가정하지 않습니다.", index))
        else:
            docker = bool(profile.get("signals", {}).get("docker"))
            changes.append(_change(
                server, "application", "modify" if docker else "unknown",
                "Amazon ECS on Fargate (검토 후보)" if docker
                else "Amazon ECS on Fargate (컨테이너화 가능성 확인 필요)",
                ("저장소에 Docker 구성 단서가 있지만 실제 컨테이너 배포·OS 의존성·"
                 "상태 저장/파일 경로·헬스체크 검증 전입니다." if docker else
                 "Linux이지만 컨테이너 빌드/상태·배포 방식이 확인되지 않아 이전 적합성 미정입니다."),
                index, ["repository-analysis.json#/signals/docker"] if docker else []))
    if role == "proxy":
        changes.append(_change(
            server, "proxy", "modify", "Application Load Balancer (후보)",
            "기존 웹서버의 라우팅·TLS 종료·URL 재작성/인증 기능을 ALB로 대체할 수 있는지 검증 전입니다.", index))
    # DB 엔진이 명시되었다면 서버 역할이 application/storage여도 실제 DB 선언을 누락하지 않음.
    if db not in ("none", "unknown") or role in ("database", "mixed") and db == "unknown":
        if db in SUPPORTED_RDS:
            changes.append(_change(
                server, "database", "modify",
                "Amazon RDS for " + db + " (동일 엔진 검토 후보)",
                "DB 엔진/버전·확장기능·운영 접근·라이선스·고가용성/복구 정책 및 데이터 이전 방식 미검증.", index))
        elif db == "mongodb":
            changes.append(_change(
                server, "database", "unknown",
                "기존 MongoDB 유지 또는 문서 DB 대안 검토",
                "Amazon DocumentDB는 MongoDB와 완전 동일 제품이 아닙니다. 호환성 확인 전 자동 전환 금지.", index))
        else:
            changes.append(_change(
                server, "database", "unknown", "DB 서비스 미확정",
                "DB 종류·설치 위치·데이터 접근 및 확장 기능을 확인해야 합니다.", index))
    if role == "storage":
        changes.append(_change(
            server, "storage", "unknown", "EBS / EFS / S3 사용 방식 검토",
            "파일 시스템/공유 잠금/POSIX·객체 접근 방식 미확인으로 S3 등 자동 전환 불가.", index))
    if not changes:
        changes.append(_change(
            server, role, "unknown", "AWS 실행 대상 미정",
            "서버 역할·데이터 및 실행 의존성을 확인한 후 AWS 이전 방법을 결정하세요.", index))
    return changes


def _connection_changes(as_is, changes, strategy):
    """선언된 논리 연결만 기존 서버별 후보에 대응. 실제 네트워크 설계는 아님."""
    by_server = {s["id"]: [] for s in as_is["servers"]}
    servers = {s["id"]: s for s in as_is["servers"]}
    for change in changes:
        by_server[change["server_id"]].append({
            key: change[key] for key in ("component", "to_be_candidate", "decision", "evidence")
        })
    rows = []
    for index, connection in enumerate(as_is["connections"]):
        left, right = connection["from"], connection["to"]
        source, target = by_server[left], by_server[right]
        purpose = connection["purpose"]
        destination = servers[right]
        target_matches = {
            "application": destination["role"] in ("application", "mixed", "proxy"),
            "database": destination["db_engine"] not in ("none", "unknown") or
                        destination["role"] in ("database", "mixed") and
                        destination["db_engine"] == "unknown",
            "storage": destination["role"] == "storage",
            "other": False,
        }[purpose]
        ambiguous = len(source) != 1 or len(target) != 1
        unknown = any(c["decision"] == "unknown" for c in source + target)
        if not target_matches:
            decision = "unknown"
            reason = "연결 목적이 기타이거나 대상 서버 역할/DB 선언과 일치하지 않아 구성요소 대응 미확인."
        elif ambiguous:
            decision = "unknown"
            reason = "서버가 여러 구성요소 후보로 나뉘어 실제 연결의 출발/도착 구성요소 미확인. 후보 전체를 표시하며 임의 선택하지 않습니다."
        elif unknown:
            decision = "unknown"
            reason = "출발 또는 도착 서버의 실행 대상/호환성이 미확인으로 연결 변경 판단 보류."
        elif strategy == "rehost":
            decision = "retain"
            reason = "EC2 서버 후보 사이에서 선언된 논리 관계 유지 검토. 실제 접속 경로는 변경될 수 있으며 유지 가능성 판정이 아닙니다."
        else:
            decision = "modify"
            reason = "서버별 서비스 후보에 맞춘 접속 경로 변경 검토. 실제 연결 가능성 또는 이전 적합성 판정이 아닙니다."
        rows.append({
            "from": left, "to": right, "purpose": purpose, "decision": decision,
            "from_candidates": source, "to_candidates": target,
            "reason": reason + " 네트워크·프로토콜/포트·보안그룹·DNS·인증·실제 연결은 미검증이며 검토 분류만 제공합니다.",
            "evidence": [{"type": "user_declared_unverified",
                          "ref": "as-is-inventory.json#/connections/" + str(index)}],
            "validated": False, "change_approved": False, "network_verified": False,
        })
    return rows


def _steps():
    return [
        {"stage": "discovery", "title": "사전 조사",
         "action": "현재 서버/DB 버전·데이터 실크기·네트워크/외부연동·인증/라이선스·RTO/RPO 및 책임자 확인"},
        {"stage": "pilot", "title": "테스트 환경 검증",
         "action": "격리된 AWS 시험 환경에서 OS/DB·API·성능/보안·접속 경로 및 예상 비용 확인"},
        {"stage": "data_transfer", "title": "데이터 이전 계획",
         "action": "DB/파일의 일관성·초기 복제·증분 동기화·암호화/권한·복구 테스트 계획 수립"},
        {"stage": "validation", "title": "전환 전 검증",
         "action": "기능·데이터 건수/무결성·관측/알림·백업 복원/장애 전환 및 이해관계자 승인"},
        {"stage": "cutover", "title": "서비스 전환(Cutover)",
         "action": "승인된 변경창에서 전환 기준·DNS/라우팅·사용자 영향 모니터링 절차를 수동 수행"},
        {"stage": "rollback", "title": "복구 및 롤백(Rollback)",
         "action": "전환 중단 조건, 구환경 재개·양방향 데이터 정합성·책임자/연락 체계 검증"},
    ]


def assess_migration(as_is, profile, requirements, topology, cost):
    """대안별 변경 내역과 근거/미확인 위험. 자동 서비스 선택 없음."""
    if as_is is None or as_is["status"] == "needs_input":
        return {
            "schema_version": "1.0", "status": "needs_inventory",
            "analysis_scope": "not_started", "strategies": [],
            "risks": [], "checklist": [], "questions": [
                "온프레미스 Inventory에 현재 서버/DB 역할·네트워크 연결을 입력할 수 있나요?"
            ],
            "recommended_strategy": None, "migration_approved": False,
            "migration_ready": False, "data_transfer_verified": False,
            "cutover_downtime_minutes": None, "estimated_monthly_migration_cost_usd": None,
            "note": "As-Is 인프라 선언이 없어 마이그레이션 비교/전환 계획을 생성하지 않았습니다.",
        }
    servers = as_is["servers"]
    options = []
    for key, title in (
        ("rehost", "Rehost — 기존 실행 환경을 EC2 중심으로 이전 검토"),
        ("replatform", "Replatform — 컨테이너/관리형 서비스로 일부 변경 검토"),
    ):
        changes = []
        for i, server in enumerate(servers):
            changes.extend(_rehost(server, i) if key == "rehost" else
                           _replatform(server, i, profile))
        options.append({
            "id": key, "title": title, "status": "candidate_review_only",
            "changes": changes, "summary": dict(Counter(x["decision"] for x in changes)),
            "connection_changes": _connection_changes(as_is, changes, key),
            "approved": False, "functional_equivalence_verified": False,
            "capacity_verified": False, "security_verified": False,
            "migration_tested": False,
            "cost_usd": None,
        })
    risks = []
    def risk(code, title, question, ev, severity="review_required", strategies=None):
        risks.append(_risk(code, title, question, ev, severity, strategies))
    if any(s["role"] == "unknown" or s["os"] == "unknown" for s in servers):
        risk("MIG-OS", "서버 역할/OS 미확인", "서버별 실제 역할·OS 지원 버전과 실행 방식을 확인할 수 있나요?",
             ["as-is-inventory.json#/servers"], "blocker")
    declared_engines = {s["db_engine"] for s in servers}
    if "unknown" in declared_engines:
        risk("MIG-DB", "DB 종류/실제 배치 미확정",
             "DB가 현재 어느 서버에 있고 엔진·버전·확장 및 데이터 크기는 무엇인가요?",
             ["as-is-inventory.json#/servers"],
             "blocker" if (profile.get("signals", {}).get("relational_database") or
                           profile.get("signals", {}).get("document_database") or
                           any(s["role"] in ("database", "mixed") for s in servers))
             else "review_required")
    if declared_engines & (SUPPORTED_RDS | {"mongodb", "other"}):
        risk("MIG-DATA", "데이터 이전·정합성 미검증",
             "DB 데이터 실제 크기, 트랜잭션/복제·백업/복구와 전환 중 무결성 검증은 가능한가요?",
             ["as-is-inventory.json#/servers", "requirements-used.json"], "blocker")
    if not as_is["connections"] and len(servers) > 1:
        risk("MIG-LINK", "서버 간 의존관계 누락",
             "서버 간 통신 연결과 외부 API/인증·공유 스토리지 의존성이 빠지지 않았나요?",
             ["as-is-inventory.json#/connections"], "blocker")
    if any(s["integrations"] for s in servers):
        risk("MIG-EXTERNAL", "외부 연동·인증 경로 검토",
             "온프레미스와 연결된 외부 연동 서비스의 접근 경로/고정 IP·TLS·인증은 유지 가능한가요?",
             ["as-is-inventory.json#/servers"])
    if any(s["access"] in ("public", "unknown") for s in servers):
        risk("MIG-NET", "네트워크 접근·보안 확인",
             "현재 방화벽/UTM, 외부 노출 범위, AWS VPC/SG·DNS/인증 정책을 확인했나요?",
             ["as-is-inventory.json#/servers", "aws-topology.json"])
    if any(s["access"] == "internal" for s in servers):
        risk("MIG-HYBRID", "내부망 접근·하이브리드 연결",
             "온프레미스 연동을 유지해야 한다면 VPN/Direct Connect 및 라우팅/대역 충돌을 검토했나요?",
             ["as-is-inventory.json#/servers", "aws-topology.json"])
    if any("licensed_software" in s["constraints"] for s in servers):
        risk("MIG-LICENSE", "라이선스 반출/관리형 전환 조건",
             "OS·미들웨어·DB의 클라우드 BYOL/라이선스·지원 정책을 계약상 확인했나요?",
             ["as-is-inventory.json#/servers"], "blocker")
    if any("local_hardware" in s["constraints"] for s in servers):
        risk("MIG-HARDWARE", "온프레미스 전용 하드웨어 의존",
             "장치/드라이버 의존성 제거 또는 하이브리드 유지가 가능한가요?",
             ["as-is-inventory.json#/servers"], "blocker")
    if any("legacy_runtime" in s["constraints"] for s in servers):
        risk("MIG-LEGACY", "레거시 런타임 호환성",
             "지원 종료 OS/런타임·라이브러리가 EC2 또는 ECS에서 검증됐나요?",
             ["as-is-inventory.json#/servers"], "blocker")
    if any("regulated_data" in s["constraints"] for s in servers):
        risk("MIG-REGULATION", "규제 데이터 처리·접근/보관",
             "데이터 위치·암호화·감사·접근 제약을 보안 담당자가 승인했나요?",
             ["as-is-inventory.json#/servers", "requirements-used.json"], "blocker")
    if any("downtime_sensitive" in s["constraints"] for s in servers):
        risk("MIG-CUTOVER", "서비스 무중단/짧은 전환창 제약",
             "데이터 동기화·서비스 영향·원복 요건과 실제 다운타임 허용치가 정의됐나요?",
             ["as-is-inventory.json#/servers"], "blocker")
    if "rto_minutes" not in requirements or "rpo_minutes" not in requirements:
        risk("MIG-RTO-RPO", "복구 목표 미입력",
             "목표 RTO/RPO 및 실제 복구 테스트 증거를 제공할 수 있나요?",
             ["requirements-used.json"])
    else:
        risk("MIG-DR-TEST", "복구 목표 달성 미검증",
             "입력된 RTO/RPO를 AWS 설계/실제 복원 시험에서 충족했나요?",
             ["requirements-used.json"])
    risk("MIG-SECURITY", "운영 보안·실환경 검증 필요",
         "IAM·보안그룹·암호화·로그·백업·모니터링/취약점/장애 복구 계획을 확인했나요?",
         ["aws-topology.json", "security-operations.json"])
    risk("MIG-COST", "비용·용량 별도 검증",
         "EC2/EBS/트래픽·ALB/RDS·백업·DR·지원/라이선스를 포함한 대안별 SKU·사용량을 검증했나요?",
         ["cost-estimate.json", "requirements-used.json"])
    if profile.get("signals", {}).get("relational_database") and not (
        declared_engines & RELATIONAL):
        risk("MIG-CONFLICT-DB", "코드 DB 단서와 입력 Inventory 불일치 가능",
             "실제 관계형 DB가 별도 서버나 외부 SaaS에서 운영 중인가요?",
             ["repository-analysis.json#/signals/relational_database",
              "as-is-inventory.json#/servers"], "blocker")
    questions = list(dict.fromkeys(x["question"] for x in risks))
    status = "assessment_draft_review_required"
    return {
        "schema_version": "1.0", "status": status,
        "analysis_scope": "user_declared_inventory_and_static_code_only",
        "inventory_verified": False, "reference_design_verified": False,
        "strategies": options, "risks": risks,
        "blocking_risk_ids": [x["id"] for x in risks if x["severity"] == "blocker"],
        "checklist": _steps(), "questions": questions,
        "recommended_strategy": None, "migration_approved": False,
        "migration_ready": False, "data_transfer_verified": False,
        "cutover_downtime_minutes": None, "estimated_monthly_migration_cost_usd": None,
        "pricing_reference_status": cost["status"], "aws_topology_reference": topology["pattern"],
        "refactor_status": "deferred_unassessed",
        "references": REFERENCES,
        "note": ("두 전략 모두 검토용 후보입니다. 대상 AWS 서비스·수량·호환성·데이터 이전/전환시간/"
                 "전체 비용·보안·SLO를 증명하지 못했으며 자동 배포·실제 이전을 수행하지 않습니다."),
    }


def markdown_migration(report):
    rows = ["# 온프레미스 → AWS Migration Assessment — 검토 초안", "",
            "> **사용자 선언 및 코드 정적 분석만 사용**. 실제 이전 가능성·보안·비용 검증 또는 승인 없음.",
            "", "- 상태: " + report["status"], "- 권장 전략 자동 확정: 없음",
            "- 운영 전환/다운타임/전체 이전 비용: 미산정·미검증", ""]
    if report["status"] == "needs_inventory":
        return "\n".join(rows + [
            "## 입력 필요", "",
            "먼저 .architecture/onprem-inventory.json의 서버·DB·연결 별칭을 작성하세요.",
            "현재 환경을 확인하지 못해 Rehost/Replatform 전략별 변환을 생성하지 않습니다.", ""
        ])
    for option in report["strategies"]:
        rows += ["## " + option["title"], "",
                 "- 상태: " + option["status"] + " / 사람 검토·승인 필요", "",
                 "| 현재 서버 | 구성 요소 | 검토 변화 | AWS 후보 | 검토 근거 |",
                 "| --- | --- | --- | --- | --- |"]
        for x in option["changes"]:
            refs = ", ".join(e["ref"] for e in x["evidence"])
            rows.append("| " + x["server_id"] + " | " + x["component"] +
                        " | " + x["decision"] + " | " + x["to_be_candidate"] +
                        " | " + x["reason"] + " (" + refs + ") |")
        rows.append("")
        rows += ["### 선언된 연결의 변경 검토", "",
                 "유지/변경/미확인은 논리 관계에 대한 검토 분류이며 실제 연결 검증·이전 가능성·승인이 아닙니다.", ""]
        connections = option.get("connection_changes", [])
        if not connections:
            rows += ["- 연결 선언 없음 — 실제 연결이 없다는 의미가 아니며 연결을 생성하지 않았습니다.", ""]
            continue
        rows += ["| 선언된 연결 | 목적 | 검토 분류 | 출발 후보 | 도착 후보 | 근거·확인할 사항 |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for x in connections:
            endpoints = ["; ".join(c["component"] + ": " + c["to_be_candidate"] +
                                  " (" + ", ".join(e["ref"] for e in c["evidence"]) + ")"
                                  for c in x[key])
                         for key in ("from_candidates", "to_candidates")]
            decision = {"retain": "유지 검토", "modify": "변경 검토", "unknown": "미확인"}[x["decision"]]
            refs = ", ".join(e["ref"] for e in x["evidence"])
            rows.append("| " + " | ".join([
                x["from"] + " → " + x["to"], x["purpose"], decision,
                *endpoints, x["reason"] + " (" + refs + ")",
            ]) + " |")
        rows.append("")
    rows += ["## 우선 확인할 위험", ""]
    for x in report["risks"]:
        rows += ["- [" + x["id"] + ", " + x["severity"] + "] " + x["title"] +
                 ": " + x["question"] + " (근거: " + ", ".join(x["evidence"]) + ")"]
    rows += ["", "## 전환 절차 검토용 체크리스트 (자동 실행 없음)", ""]
    for i, x in enumerate(report["checklist"], 1):
        rows += [str(i) + ". **" + x["title"] + "** — " + x["action"]]
    rows += ["", "## 추가 설명", "",
             "- Rehost와 Replatform은 AWS의 7 Rs 중 검토용 두 대안입니다. Refactor는 분석하지 않았습니다.",
             "- 사용자가 입력한 서버 디스크 용량은 실제 DB 데이터 크기/이전 시간의 증거가 아닙니다.",
             "- 기존 비용 시나리오가 계산되더라도 이 두 전략의 총비용으로 전용하지 않습니다.",
             "- 전략은 우열·이전 가능성/ROI/작업 시간·다운타임을 자동 판정하지 않습니다.",
             "", report["note"], ""]
    return "\n".join(rows)
