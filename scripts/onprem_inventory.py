"""온프레미스 현황의 최소 선언형 Inventory: 신뢰 경계, 안전한 JSON과 출처 보존.

운영 인프라 자동 진단 기능이 아닙니다. 실제 구성/설치/접속 확인은 수행하지 않습니다.
기기 식별자·주소·로그·포트·자격증명 등 민감 원문을 입력받지 않습니다.
"""
import json
import math
from pathlib import Path
import re

MAX_BYTES = 16384
MAX_SERVERS = 8
MAX_CONNECTIONS = 16
ID = re.compile(r"[a-z][a-z0-9_-]{0,23}\Z")
ROLES = {"application", "database", "proxy", "storage", "mixed", "unknown"}
SYSTEMS = {"linux", "windows", "unknown"}
DBS = {"postgresql", "mysql", "mariadb", "sqlserver", "oracle", "mongodb",
       "other", "none", "unknown"}
ACCESS = {"internal", "public", "unknown"}
PURPOSE = {"application", "database", "storage", "other"}
CONSTRAINTS = {"downtime_sensitive", "licensed_software", "local_hardware",
               "legacy_runtime", "regulated_data"}
SERVER_FIELDS = {"id", "role", "os", "cpu_cores", "memory_gb", "storage_gb",
                 "db_engine", "access", "integrations", "constraints"}


def _no_duplicate_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Inventory JSON에 중복된 키를 사용할 수 없습니다.")
        obj[key] = value
    return obj


def _id(value, field):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(field + "은 주소/호스트명 대신 짧은 영문 별칭(a-z, 0-9, _,-)만 허용합니다.")
    return value


def _enum(value, valid, field):
    if not isinstance(value, str) or value not in valid:
        raise ValueError(field + "은 허용된 항목 또는 unknown이어야 합니다.")
    return value


def _capacity(value, field, upper):
    if value == "unknown":
        return "unknown"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
        not math.isfinite(value) or value <= 0 or value > upper
    ):
        raise ValueError(field + "은 양수 또는 unknown이어야 합니다.")
    return value


def _list(values, field, *, choices=None, limit=6):
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError(field + "은 최대 " + str(limit) + "개 배열이어야 합니다.")
    if choices is not None:
        for value in values:
            _enum(value, choices, field)
    else:
        for value in values:
            _id(value, field)
    if len(set(values)) != len(values):
        raise ValueError(field + "에 중복 항목이 있습니다.")
    return sorted(values)


def validate_inventory(data):
    """정확히 한정된 구조/데이터 유형만 허용. 불명확한 연결은 빈 리스트로 남깁니다."""
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "servers", "connections"
    } or data["schema_version"] != "1.0":
        raise ValueError("Inventory schema_version 1.0과 servers/connections가 필요합니다.")
    servers = data["servers"]
    connections = data["connections"]
    if not isinstance(servers, list) or not 1 <= len(servers) <= MAX_SERVERS:
        raise ValueError("Inventory에는 1~8개 서버가 필요합니다.")
    if not isinstance(connections, list) or len(connections) > MAX_CONNECTIONS:
        raise ValueError("Inventory 연결은 16개 이하로 제한합니다.")
    known = set()
    normalized = []
    for row in servers:
        if not isinstance(row, dict) or not set(row).issubset(SERVER_FIELDS) or "id" not in row:
            raise ValueError("서버에는 id와 허용된 구성 필드만 사용할 수 있습니다.")
        ident = _id(row["id"], "서버 별칭")
        if ident in known:
            raise ValueError("중복 서버 별칭은 허용하지 않습니다.")
        known.add(ident)
        host = {"id": ident, "source": "user_declared_unverified",
                "provided_fields": sorted(set(row) - {"id"})}
        for field, valid in (("role", ROLES), ("os", SYSTEMS),
                             ("db_engine", DBS), ("access", ACCESS)):
            host[field] = _enum(row.get(field, "unknown"), valid, field)
        for field, upper in (("cpu_cores", 1024), ("memory_gb", 1048576),
                             ("storage_gb", 1073741824)):
            host[field] = _capacity(row.get(field, "unknown"), field, upper)
        host["integrations"] = _list(row.get("integrations", []), "integrations")
        host["constraints"] = _list(row.get("constraints", []), "constraints",
                                    choices=CONSTRAINTS)
        normalized.append(host)
    links = []
    seen = set()
    for row in connections:
        if not isinstance(row, dict) or set(row) != {"from", "to", "purpose"}:
            raise ValueError("연결에는 from/to/purpose만 사용할 수 있습니다.")
        left, right = _id(row["from"], "연결 출발"), _id(row["to"], "연결 도착")
        purpose = _enum(row["purpose"], PURPOSE, "연결 목적")
        if left not in known or right not in known or left == right:
            raise ValueError("연결 대상은 서로 다른 등록 서버여야 합니다.")
        edge = (left, right, purpose)
        if edge in seen:
            raise ValueError("중복된 연결은 허용하지 않습니다.")
        seen.add(edge)
        links.append({"from": left, "to": right, "purpose": purpose,
                      "source": "user_declared_unverified"})
    return {"schema_version": "1.0", "servers": normalized,
            "connections": sorted(links, key=lambda x: (x["from"], x["to"], x["purpose"])),
            "source": "user_declared_unverified", "verified": False}


def read_inventory(root, path=None):
    """명시 경로 우선. 없으면 기본 파일을 찾되 외부/심볼릭 링크는 거부."""
    base = Path(root).resolve()
    if not path:
        path = ".architecture/onprem-inventory.json"
        if not (base / path).exists() and not (base / path).is_symlink():
            return None
    selected = base / path
    # 직접/중간 경로의 심볼릭 링크 거부 및 리포지토리 외부 경로 차단
    if selected.is_symlink() or any(p.is_symlink() for p in selected.parents if p != base):
        raise ValueError("온프레미스 Inventory는 심볼릭 링크를 사용할 수 없습니다.")
    file = selected.resolve()
    if (not file.is_relative_to(base) or file.suffix.lower() != ".json" or
            not file.is_file() or file.stat().st_size > MAX_BYTES):
        raise ValueError("Inventory는 저장소 내부 16KB 이하 JSON 파일이어야 합니다.")
    try:
        return validate_inventory(json.loads(
            file.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("비정상 숫자")),
        ))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("온프레미스 Inventory JSON을 읽을 수 없습니다.") from exc


def assess_inventory(inventory, profile):
    """사용자 선언과 코드에서 관측한 단서를 분리해 As-Is '후보' 보고서로 묶습니다."""
    if inventory is None:
        return {
            "schema_version": "1.0", "status": "needs_input",
            "source": None, "verified": False,
            "onprem_environment_checked": False,
            "servers": [], "connections": [], "code_observations": [],
            "questions": [
                "온프레미스 서버(역할/OS/자원)와 DB 위치는 어디인가요?",
                "실제 서버 간 통신 연결과 내부/외부 접근 범위를 확인할 수 있나요?",
            ],
            "migration_assessment_performed": False,
            "note": "현재 서버·DB·네트워크를 조사하지 않았습니다. 코드 관찰로 배치 정보를 추정하지 않습니다.",
        }
    signals = profile.get("signals", {})
    observations = []
    for key, label in (
        ("relational_database", "관계형 DB 관련 코드/설정 단서"),
        ("document_database", "문서형 DB 관련 코드/설정 단서"),
        ("docker", "Docker 관련 구성 단서"),
        ("api_routes", "API 라우트 관련 단서"),
    ):
        if signals.get(key):
            observations.append({
                "signal": key, "label": label, "source": "repository_code_signal",
                "evidence_file": "repository-analysis.json",
                "deployment_location_verified": False,
            })
    questions = []
    servers = inventory["servers"]
    if any(s["role"] == "unknown" or s["os"] == "unknown" or
           s["db_engine"] == "unknown" or s["access"] == "unknown" or
           s["cpu_cores"] == "unknown" or s["memory_gb"] == "unknown" or
           s["storage_gb"] == "unknown" for s in servers):
        questions.append("일부 서버 역할·OS·용량·DB/접근 정보가 unknown입니다.")
    if not inventory["connections"] and len(servers) > 1:
        questions.append("서버 간 연결이 입력되지 않았습니다. 실제 연결이 없다는 의미가 아닙니다.")
    declared = {s["db_engine"] for s in servers}
    if signals.get("relational_database") and declared <= {"none", "mongodb", "unknown"}:
        questions.append("코드에 관계형 DB 단서가 있지만 등록 서버에서 확인된 관계형 DB가 없습니다. DB의 실제 위치를 확인하세요.")
    if signals.get("document_database") and declared <= {"none", "postgresql", "mysql", "mariadb", "sqlserver", "oracle", "unknown"}:
        questions.append("코드의 문서형 DB 단서와 입력 서버 DB 정보의 관계를 확인하세요(추가 원격 DB 가능).")
    if any(s["access"] == "public" for s in servers):
        questions.append("외부 공개 접근 선언이 있습니다. 방화벽/UTM 및 인증 정책은 검증하지 않았습니다.")
    return {
        "schema_version": "1.0", "status": "declared_review_required",
        "source": "user_declared_unverified", "verified": False,
        "onprem_environment_checked": False,
        "servers": servers, "connections": inventory["connections"],
        "code_observations": observations,
        "questions": questions,
        "migration_assessment_performed": False,
        "note": ("서버/DB/연결은 사용자 입력이며 실제 환경에서 확인하지 않았습니다. "
                 "코드 단서는 서버 배치·연결 관계의 증명이 아니며 AWS 이전 방식은 아직 평가하지 않았습니다."),
    }


def markdown_inventory(report):
    lines = ["# 온프레미스 As-Is — 사용자 선언 기반, 검증 전", "",
             "> 실제 서버·네트워크 접속이나 자동 수집은 하지 않았습니다.",
             "", "- 상태: " + report["status"],
             "- 실제 운영 환경 확인: 미실시", "- AWS Migration Assessment: 미실시", ""]
    if report["status"] == "needs_input":
        return "\n".join(lines + [
            "## Inventory 입력 대기", "",
            "선택형 `.architecture/onprem-inventory.json`을 준비하면 선언형 As-Is 도면을 만듭니다.",
            "DB 패키지 발견만으로 실제 서버/DB 위치를 추정하지 않습니다.", "",
        ])
    lines.extend(["## 입력된 서버 목록", "",
                  "| 별칭 | 역할 | OS | CPU | 메모리 GB | 스토리지 GB | DB | 외부 접근 | 출처 |",
                  "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |"])
    for s in report["servers"]:
        lines.append("| " + " | ".join(str(s[k]) for k in (
            "id", "role", "os", "cpu_cores", "memory_gb", "storage_gb", "db_engine",
            "access", "source",
        )) + " |")
    lines += ["", "## 사용자가 명시한 연결만 표시", ""]
    if report["connections"]:
        lines += ["- " + e["from"] + " → " + e["to"] + " (" + e["purpose"] +
                  ", 사용자 선언)" for e in report["connections"]]
    else:
        lines.append("- 연결 선언 없음 — 연결이 없다는 뜻이 아님")
    lines += ["", "## 코드 관찰 (서버에 자동 할당하지 않음)", ""]
    lines += ["- " + x["label"] + " (" + x["evidence_file"] + ")"
              for x in report["code_observations"]]
    if not report["code_observations"]:
        lines.append("- 지원 범위의 명시적인 기술 단서 미관측. 실제 미설치 여부는 알 수 없음.")
    lines += ["", "## 확인 질문", ""]
    lines += ["- " + x for x in report["questions"][:5]]
    lines += ["", report["note"], ""]
    return "\n".join(lines)
