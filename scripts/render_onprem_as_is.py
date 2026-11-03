"""사용자 선언형 온프레미스 As-Is의 독립 오프라인 SVG 렌더러.

외부 이미지/JS/네트워크 자원 없음. 실제 IP·호스트 위치·연결을 추정하지 않음.
"""
from html import escape
from pathlib import Path


LABELS = {
    "application": "앱/API", "database": "DB 서버", "proxy": "프록시",
    "storage": "스토리지", "mixed": "복합 서버", "unknown": "역할 미확인",
    "linux": "Linux", "windows": "Windows", "postgresql": "PostgreSQL",
    "mysql": "MySQL", "mariadb": "MariaDB", "sqlserver": "SQL Server",
    "oracle": "Oracle DB", "mongodb": "MongoDB", "other": "기타",
    "none": "없음(사용자 선언)", "internal": "내부", "public": "외부 공개",
}


def _text(x):
    return escape(str(x), quote=True)


def render_as_is_svg(report, output):
    """서버·관계선은 Inventory로 직접 선언된 것만 그림. 기본 미확인은 별도 설명."""
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = len(report["servers"])
    rows = max(1, (count + 1) // 2)
    table_top = 120 + rows * 178
    height = table_top + 110 + len(report["connections"]) * 28
    width = 940
    blocks = [
        "<svg xmlns='http://www.w3.org/2000/svg' width='940' height='" + str(height) +
        "' viewBox='0 0 940 " + str(height) + "' role='img' aria-label='온프레미스 사용자 선언 As-Is 구성도'>",
        "<rect width='940' height='" + str(height) + "' fill='#f6f9fc'/>",
        "<text x='32' y='42' font-family='sans-serif' font-size='23' font-weight='700' fill='#18395d'>온프레미스 As-Is · 사용자 입력</text>",
        "<text x='32' y='68' font-family='sans-serif' font-size='14' fill='#9c4c08'>실제 장비/접속/서버 배치 검증 전 · AWS 제안도가 아님</text>",
    ]
    if not count:
        blocks += [
            "<rect x='32' y='100' width='876' height='110' rx='12' fill='#fff8e7' stroke='#e9be74'/>",
            "<text x='54' y='144' font-family='sans-serif' font-size='17' fill='#764819'>기존 인프라 미입력</text>",
            "<text x='54' y='174' font-family='sans-serif' font-size='14' fill='#764819'>서버·DB·네트워크를 코드만으로 확정하지 않습니다.</text>",
        ]
    for i, server in enumerate(report["servers"]):
        col, row = i % 2, i // 2
        x, y = 32 + col * 448, 92 + row * 178
        role = LABELS.get(server["role"], server["role"])
        db = LABELS.get(server["db_engine"],server["db_engine"])
        os_name = LABELS.get(server["os"], server["os"])
        access = LABELS.get(server["access"], server["access"])
        lines = [
            ("별칭: " + server["id"] + "   [" + role + "]", 25, "17", "#163c63"),
            ("OS: " + os_name + "   CPU: " + str(server["cpu_cores"]) +
             "   RAM: " + str(server["memory_gb"]) + " GB", 62, "14", "#38516b"),
            ("스토리지: " + str(server["storage_gb"]) + " GB   DB: " + db, 87, "14", "#38516b"),
            ("접근: " + access + " / 사용자 선언(검증 전)", 112, "13", "#8b5a17"),
        ]
        blocks.append("<rect x='" + str(x) + "' y='" + str(y) +
                      "' width='428' height='146' rx='12' fill='#fff' stroke='#a9c1d8'/>")
        for line, dy, size, color in lines:
            blocks.append("<text x='" + str(x + 18) + "' y='" + str(y + dy) +
                          "' font-size='" + size + "' font-family='sans-serif' fill='" + color +
                          "'>" + _text(line) + "</text>")
    blocks += [
        "<rect x='32' y='" + str(table_top) +
        "' width='876' height='" + str(height - table_top - 20) +
        "' rx='12' fill='#eef3f8'/>",
        "<text x='50' y='" + str(table_top + 30) +
        "' font-size='17' font-family='sans-serif' font-weight='700' fill='#18395d'>명시된 서버 간 관계만 표시</text>",
    ]
    if report["connections"]:
        for i, edge in enumerate(report["connections"]):
            name = edge["from"] + "  →  " + edge["to"] + "   [" + edge["purpose"] + "]"
            blocks.append("<text x='56' y='" + str(table_top + 62 + 28 * i) +
                          "' font-size='14' font-family='sans-serif' fill='#38516b'>" +
                          _text(name) + "</text>")
    else:
        blocks.append("<text x='56' y='" + str(table_top + 62) +
                      "' font-size='14' font-family='sans-serif' fill='#8b5a17'>연결 미입력 · 연결이 없다는 의미가 아닙니다.</text>")
    blocks.append("</svg>")
    target.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return {"file": target.name, "status": "user_declared_unverified",
            "nodes": count, "declared_edges": len(report["connections"]),
            "external_resources": False}
