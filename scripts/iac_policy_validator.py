"""Terraform plan JSON 정적 안전 점검 — 실행/계정 조회 없이 확인된 설정만 검사.

terraform show -json 파일에는 민감정보가 포함될 수 있습니다. 입력 파일의
원문/리소스 주소/설정값을 산출물에 기록하지 않으며 R001 식별자로 익명화합니다.
"""
import json
from pathlib import Path
import re

MAX_BYTES = 8 * 1024 * 1024
MAX_RESOURCES = 1500
DANGEROUS_CIDRS = {"0.0.0.0/0", "::/0"}
RULES = {
    "TF-SEC-001": ("critical", "보안 그룹의 공개 관리 포트", "SSH/RDP 또는 모든 포트의 공개 접근을 제한하세요."),
    "TF-SEC-002": ("review_required", "보안 그룹의 공개 접근", "공개 CIDR의 허용 포트와 접속 목적을 검토하세요."),
    "TF-SEC-003": ("critical", "S3 공개 ACL", "공개 ACL을 제거하고 정책·Public Access Block을 확인하세요."),
    "TF-SEC-004": ("critical", "RDS 공개 접근", "DB의 인터넷 연결을 제거하고 비공개 서브넷을 검토하세요."),
    "TF-SEC-005": ("critical", "RDS 저장 데이터 암호화 명시적 해제", "DB 암호화를 활성화하세요."),
    "TF-SEC-006": ("critical", "S3 Public Access Block 명시적 비활성화",
                   "기존 계정/조직 보호 설정을 점검하고 필요한 접근 차단을 활성화하세요."),
    "TF-SEC-007": ("critical", "IAM 전체 리소스에 전체 작업 허용",
                   "허용 작업·리소스를 최소 권한 범위로 제한하세요."),
    "TF-SEC-008": ("review_required", "설정 값 미확정",
                   "알 수 없는 값은 배포 전 확정하여 검사하세요."),
}
ALLOWED_RESOURCE_TYPES = {
    "aws_security_group", "aws_security_group_rule",
    "aws_vpc_security_group_ingress_rule", "aws_s3_bucket", "aws_s3_bucket_acl",
    "aws_s3_bucket_public_access_block", "aws_db_instance",
    "aws_iam_policy", "aws_iam_role_policy",
}


def read_terraform_plan(root, path):
    if not path:
        return None
    repo = Path(root).resolve()
    location = (repo / path).resolve()
    if not location.is_relative_to(repo) or location.is_symlink():
        raise ValueError("Terraform plan JSON은 저장소 내부 일반 파일이어야 합니다.")
    if not location.is_file() or location.stat().st_size > MAX_BYTES:
        raise ValueError("Terraform JSON이 없거나 8MB를 초과했습니다.")
    try:
        doc = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("Terraform plan JSON을 읽을 수 없습니다.") from exc
    if not isinstance(doc, dict) or "format_version" not in doc or not isinstance(doc.get("resource_changes"), list):
        raise ValueError("terraform show -json으로 생성한 plan JSON의 resource_changes가 필요합니다.")
    if len(doc["resource_changes"]) > MAX_RESOURCES:
        raise ValueError("검사 가능한 자원 변경 수 상한(1500)을 초과했습니다.")
    return doc


def _all_access(from_port, to_port, protocol):
    try:
        low, high = int(from_port), int(to_port)
    except (TypeError, ValueError):
        return False
    if protocol == "-1":
        return True
    if str(protocol).lower() not in ("tcp", "6"):
        return False
    return (low <= 22 <= high or low <= 3389 <= high)


def _cidr_public(value):
    return isinstance(value, str) and value in DANGEROUS_CIDRS


def _policy_wildcard(policy):
    if not policy:
        return False
    try:
        value = json.loads(policy) if isinstance(policy, str) else policy
    except (ValueError, TypeError):
        return False
    if not isinstance(value, dict):
        return False
    statement = value.get("Statement", [])
    if isinstance(statement, dict):
        statement = [statement]
    for item in statement if isinstance(statement, list) else []:
        if not isinstance(item, dict) or item.get("Effect") != "Allow":
            continue
        actions = item.get("Action", [])
        resources = item.get("Resource", [])
        if actions == "*" or (isinstance(actions, list) and "*" in actions):
            if resources == "*" or (isinstance(resources, list) and "*" in resources):
                return True
    return False


def inspect_terraform_plan(document):
    if document is None:
        return {
            "status": "not_scanned", "scan_type": "terraform_plan_json",
            "scanned_changes": 0, "scanned_supported_resources": 0,
            "findings": [], "counts": {"critical": 0, "review_required": 0},
            "production_ready": False,
            "note": "Terraform plan 파일이 없어 IaC 검사 자체를 수행하지 않았습니다.",
        }
    changes = [c for c in document["resource_changes"]
               if isinstance(c, dict) and c.get("mode", "managed") == "managed" and
               isinstance(c.get("change"), dict) and
               not set(c["change"].get("actions", [])) == {"delete"}]
    findings = []
    supported = 0
    def report(rule, reference, resource_type):
        severity, title, action = RULES[rule]
        findings.append({
            "rule_id": rule, "severity": severity, "resource_ref": reference,
            "resource_type": resource_type, "title": title,
            "recommended_action": action,
            "evidence": "terraform_plan.resource_changes.change.after",
            "validation": "정적 Terraform plan 값 검사; 클라우드 상태 검증 아님",
        })
    for index, item in enumerate(changes, 1):
        typ = item.get("type")
        if typ not in ALLOWED_RESOURCE_TYPES:
            continue
        supported += 1
        ref = "R" + str(index).zfill(4)
        change = item["change"]
        after = change.get("after") or {}
        unknown = change.get("after_unknown") or {}
        if not isinstance(after, dict):
            continue
        if not isinstance(unknown, dict):
            unknown = {}
        if unknown:
            report("TF-SEC-008", ref, typ)
        if typ in {"aws_security_group", "aws_security_group_rule",
                   "aws_vpc_security_group_ingress_rule"}:
            rules = after.get("ingress") if typ == "aws_security_group" else [after]
            if not isinstance(rules, list):
                rules = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if typ == "aws_security_group_rule" and rule.get("type") != "ingress":
                    continue
                cidrs = (rule.get("cidr_blocks") or []) + (rule.get("ipv6_cidr_blocks") or [])
                if typ == "aws_vpc_security_group_ingress_rule":
                    cidrs += [rule.get("cidr_ipv4"), rule.get("cidr_ipv6")]
                if any(_cidr_public(x) for x in cidrs):
                    if _all_access(rule.get("from_port"), rule.get("to_port"), rule.get("protocol") or rule.get("ip_protocol")):
                        report("TF-SEC-001", ref, typ)
                    else:
                        report("TF-SEC-002", ref, typ)
        if typ in {"aws_s3_bucket", "aws_s3_bucket_acl"} and after.get("acl") in {"public-read", "public-read-write", "authenticated-read"}:
            report("TF-SEC-003", ref, typ)
        if typ == "aws_db_instance":
            if after.get("publicly_accessible") is True:
                report("TF-SEC-004", ref, typ)
            if after.get("storage_encrypted") is False:
                report("TF-SEC-005", ref, typ)
        if typ == "aws_s3_bucket_public_access_block":
            if any(after.get(k) is False for k in
                   ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")):
                report("TF-SEC-006", ref, typ)
        if typ in {"aws_iam_policy", "aws_iam_role_policy"} and _policy_wildcard(after.get("policy")):
            report("TF-SEC-007", ref, typ)
    # 입력 파일 이름, 주소, 설정 원문, 정책/암호 값은 JSON/Markdown에 남기지 않음.
    critical = sum(x["severity"] == "critical" for x in findings)
    review = sum(x["severity"] == "review_required" for x in findings)
    return {
        "status": "findings" if findings else "limited_checks_no_findings",
        "scan_type": "terraform_plan_json", "scanned_changes": len(changes),
        "scanned_supported_resources": supported,
        "findings": findings, "counts": {"critical": critical, "review_required": review},
        "production_ready": False,
        "note": "검사는 일부 리소스의 명시적 설정에 한정합니다. 미탐지=보안 적합 판정이 아닙니다.",
    }


def markdown_iac(report):
    rows = ["# Terraform 계획 정적 점검", "",
            "> **실환경 보안 적합성 판정이 아닙니다.** 전체 Terraform 설정/모듈/IAM을 검사하지 않습니다.",
            "", "- 상태: " + report["status"],
            "- 검사 대상 변경: " + str(report["scanned_changes"]),
            "- 지원 리소스 변경: " + str(report["scanned_supported_resources"]),
            "- 명시적 보안 위험: " + str(report["counts"]["critical"]), "",
            "| 규칙 | 유형 | 익명 리소스 | 내용 | 조치 |",
            "| --- | --- | --- | --- | --- |"]
    for finding in report["findings"]:
        rows.append("| " + finding["rule_id"] + " | " + finding["severity"] +
                    " | " + finding["resource_ref"] + " (" + finding["resource_type"] +
                    ") | " + finding["title"] + " | " + finding["recommended_action"] + " |")
    rows += ["", report["note"], "",
             "주의: 원본 Terraform plan JSON은 민감 설정값을 포함할 수 있습니다."
             " 저장소에 커밋하지 말고 권한이 제한된 환경에서 생성·삭제하세요.", ""]
    return "\n".join(rows)
