"""사용자 중심의 두 가지 분석 목적. 온프레미스 실제 환경 추정 금지.

new_aws: 저장소 코드 기반 AWS To-Be 참조 설계
migrate_onprem: 저장소 코드 기반 후보 + 현행 온프레미스 정보 미확인 명시
Inventory/실제 Migration Assessment는 별도 후속 기능이며 여기서 수행하지 않음.
"""

GOALS = {
    "new_aws": {
        "label": "신규 서비스 AWS 구축",
        "scope": "저장소 코드·입력 요구사항 기반 AWS 참조 설계",
        "status": "reference_design_pending_review",
        "limitations": [
            "AWS 계정·실제 IAM/네트워크·부하·운영 비용 검증 전",
        ],
        "next_actions": [
            "코드·설정 탐지 근거와 서비스 선정 이유를 검토합니다.",
            "운영 리전·트래픽·DB·가용성 요구가 불명확하면 요구사항 JSON을 보완합니다.",
            "AWS 구축 전 보안·비용·부하·복구 검증을 별도로 수행합니다.",
        ],
    },
    "migrate_onprem": {
        "label": "온프레미스에서 AWS로 이전",
        "scope": "저장소 코드 기반 AWS To-Be 후보만 생성 (온프레미스 현황 미진단)",
        "status": "onprem_inventory_and_migration_assessment_unavailable",
        "limitations": [
            "온프레미스 서버·DB 위치·OS·CPU·메모리·네트워크·외부 연동을 조회하지 않았습니다.",
            "현재 버전은 온프레미스 Inventory 입력·As-Is 인프라 도면·마이그레이션 전략 평가를 지원하지 않습니다.",
            "Rehost/Replatform의 적합성, 데이터 이전·다운타임·전환/롤백 가능성을 검증하지 않았습니다.",
        ],
        "next_actions": [
            "기존 서버·DB·스토리지와 외부 연결·데이터 규모를 별도로 정리합니다.",
            "다운타임 허용치·RTO/RPO·기존 구성 변경 가능 여부를 확인합니다.",
            "현재 AWS 그림은 전환 가능 판정이 아닌 참조 후보로만 사용합니다.",
        ],
    },
}


def build_analysis_goal(goal="new_aws"):
    """잘못된 입력은 기본값으로 조용히 대체하지 않고 거부합니다."""
    if not isinstance(goal, str) or goal not in GOALS:
        raise ValueError("analysis_goal은 new_aws 또는 migrate_onprem만 허용합니다.")
    config = GOALS[goal]
    return {
        "schema_version": "1.0",
        "goal": goal,
        "label": config["label"],
        "scope": config["scope"],
        "status": config["status"],
        "limitations": list(config["limitations"]),
        "next_actions": list(config["next_actions"]),
        "aws_account_checked": False,
        "onprem_inventory_analyzed": False,
        "migration_assessment_performed": False,
        "architecture_approved": False,
        "deployed": False,
    }
