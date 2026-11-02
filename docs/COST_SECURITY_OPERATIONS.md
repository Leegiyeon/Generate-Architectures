# 비용 산정·IaC 보안 점검·유지보수 운영 가이드

> 기준: 2026-11-02. 이 도구는 **AWS Solutions Architect의 초안 검토를 보조**할 뿐, AWS 결제액·법적 적합성·보안 안전성·SLA 달성을 보증하지 않습니다.

## 1. 사용자가 먼저 알아야 할 중요한 조건

| 항목 | 현재 구현 범위 | 사용자가 해야 할 일 |
| --- | --- | --- |
| 기본 비용 보고 | 사용량·단가가 없으면 **미산정** 처리 | 리전, 월 사용량, 정확한 서비스/SKU 및 가격 근거 제공 |
| 사용량 기반 시나리오 | 확인된 단가 × 예상 수량 | 피크와 평균값, 로그/백업/전송/NAT 등 빠진 항목 확인 |
| AWS 공식 단가 조회 | 명시적 활성화 시 AWS Price List GetProducts 단일 SKU/단일 무조건 온디맨드 가격 조회 | AWS IAM 임시 자격증명 및 조회 상품 필터 설정 |
| IaC 보안 점검 | Terraform **plan JSON의 명시적 값 일부만** 검사 | `terraform show -json`으로 생성하되 원문 유출 및 Git 추적 방지 |
| 자동 추천 | 기존 규칙 기반 AWS 참조 패턴은 유지 | 예산·SLO·RTO/RPO·데이터 민감도 등 실제 요구사항 확인 |
| 검증/배포 | 실제 AWS 리소스 조회, terraform apply, 비용 청구서 조회 **없음** | 최종 승인과 실제 운영 검증을 별도 수행 |

`cost-estimate.json/md`, `iac-policy.json/md` 결과는 모두 영어 코드값 + 한국어 설명으로 저장됩니다. 기본 실행에서 둘 다 사용자의 명시적 입력이 없으면 **미산정/미검사**로 표시되며 합격 처리하지 않습니다.

## 2. 비용 산정 방식과 실행

예제 파일 `.architecture/cost.example.json`을 `.architecture/cost.json`으로 복사하여 **실제 프로젝트에 해당하는 사용량과 상품별 가격 소스**를 입력합니다. 미확인 단가는 반드시 `kind: unknown`으로 둡니다.

```json
{
  "region": "ap-northeast-2",
  "items": [
    {
      "id": "lambda_requests",
      "quantity": 1000000,
      "unit": "Requests",
      "rate": {
        "kind": "aws_price_list",
        "service_code": "AWSLambda",
        "filters": {"group": "AWS-Lambda-Requests"}
      }
    }
  ]
}
```

`group` 같은 상품 필터는 **실제 AWS Price List 속성과 일치하는지 확인해야 합니다**. 필터에 맞는 상품이 둘 이상이거나 종량제 가격 구간이 여러 개인 경우 금액을 임의 선택하지 않고 `unpriced`로 처리합니다.

수동으로 확인한 공식 AWS 요율이 있다면 `rate`에 `{"kind":"manual_quote", "unit_price_usd":"0.1234", "source":"https://aws.amazon.com/s3/pricing/", "as_of":"2026-11-02"}` 형식으로 넣습니다. 이 출처는 **사용자가 제공한 가격 근거이며 시스템이 가격을 외부 검증한 것은 아닙니다**. 단가 기준일을 남겨 추후 변경 시 교체할 수 있습니다.

```bash
# 외부 AWS 인증 없이 입력 단가만 계산 (단가 미입력 시 월간 총액 없음)
python3 scripts/recommend_architecture.py --repo . --output architecture-output --cost-input .architecture/cost.json

# 임시 AWS 자격증명 + boto3 준비 후 명시적 Price List 조회
python3 -m pip install boto3==1.40.0
python3 scripts/recommend_architecture.py --repo . --output architecture-output --cost-input .architecture/cost.json --live-pricing
```

**중요:** `--live-pricing`은 AWS Price List의 상품 단가 조회만 합니다. 계정 사용량을 자동으로 조회하지 않으며, AWS Cost Explorer/청구서·Credit·Savings Plans·Reserved Instances·무료 할당량/세금/환율을 반영하지 않습니다. 한 상품이라도 단가가 미확인되면 `monthly_total_usd: null`로 유지됩니다. 표시된 부분 합계도 전체 AWS 예산과 다릅니다.

AWS 공식 Price List Query API는 SDK의 `pricing.get_products`를 사용하며, API 엔드포인트 리전(`us-east-1`)과 **상품 지역 속성(`regionCode`)은 서로 다릅니다**. API는 서명된 AWS 자격증명이 필요합니다.

## 3. AWS 권한 보안

**AWS 키를 GitHub 저장소 코드·workflow YAML·Actions 로그·AI 프롬프트에 넣지 마세요.** 기존 Access Key를 지속 저장하기보다 GitHub OIDC로 만료되는 역할 임시 권한을 사용하는 것을 권장합니다.

최소 요구 권한은 `pricing:GetProducts` 입니다. 이 조회를 위한 AWS 계정 역할에는 `ec2:*`, `iam:*`, `s3:*`, `terraform apply` 같은 권한을 부여하지 않습니다.

IAM 예시(배포 권한을 포함하지 않는 가격 읽기 전용):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["pricing:GetProducts"],
    "Resource": "*"
  }]
}
```

이는 **계정 IAM 역할 권한 정책의 예시**입니다. OIDC를 사용하려면 별도로 GitHub 토큰의 `aud`·`sub`를 정확한 조직/저장소/브랜치 또는 Environment로 제한한 **역할 신뢰 정책**이 필요합니다. 특히 PR 이벤트에서 AWS 자격증명 발급을 허용하지 않는 것이 안전합니다.

현재 본 저장소의 기본 Actions 워크플로는 **AWS OIDC 자격증명 발급을 설정하지 않습니다.** 따라서 Secrets/IAM 역할 연결을 별도로 하지 않는 한 live pricing은 활성화해도 조회가 실패한 상태로 남습니다. 이는 정상적인 안전 기본값입니다.

## 4. Terraform 보안 점검 — 반드시 사전에 이해할 사항

`terraform show -json` 파일에는 비밀키·DB 자격증명·기타 민감 필드가 포함될 수 있습니다.

- 이 파일을 Git에 커밋하지 않습니다. 추가한 `.gitignore`에는 `*.tfplan`, `terraform-plan*.json`, `*.tfstate` 등을 포함했습니다. **.gitignore는 이미 추적 중인 파일이나 다른 파일명, 실수로 force add한 내용까지 막지는 못합니다.** 별도의 pre-commit 시크릿 탐지·GitHub secret scanning을 권장합니다.
- 가능한 한 **개발용/격리된 환경에서 임시 파일로 작성**하고, 사용자 권한을 제한한 뒤 점검 종료 후 원본을 삭제합니다. 원본 JSON을 이메일·PR 댓글·Actions Artifact·외부 AI로 보내지 않습니다.
- 이 스캐너는 Terraform 및 provider 실행이나 외부 모듈 다운로드를 수행하지 않습니다. 이미 생성된 `resource_changes[].change.after`를 읽습니다.
- 현 단계는 공개 보안 그룹의 관리 포트, S3 공개 ACL·Public Access Block 명시적 비활성화, RDS 공개 접근/암호화 비활성화, IAM 전체 작업·리소스 허용 등을 **일부만 확인**합니다. 새 유형의 리소스, Terraform 동적 구성, 조직 정책·SCP·실제 AWS 적용 상태 등은 별도 점검이 필요합니다.
- 점검 산출물에는 임의의 리소스 주소/속성 원문 대신 **R0001 형태의 익명 ID와 규칙 ID**만 저장합니다. 다만 점검 대상 자원 유형 정보는 포함되므로 출력물도 접근을 제한하세요.

실행 예시:

```bash
# 기존 Terraform 실행 환경에서만 예시. 아래 명령은 Generate-Architectures가 실행하지 않습니다.
terraform plan -out=review.tfplan
terraform show -json review.tfplan > .architecture/terraform-plan.json

# 로컬 정적 검사
python3 scripts/recommend_architecture.py --repo . --output architecture-output --terraform-plan .architecture/terraform-plan.json

# 원본 파일은 별도로 안전하게 삭제. macOS/Linux에서 SSD 보안 삭제는 파일 삭제와 별도 정책에 따름.
rm .architecture/terraform-plan.json review.tfplan
```

**주의:** 최초 `terraform plan` 실행 자체가 공급자에게 요청을 보내거나 상태 파일을 접근할 수 있습니다. 프로덕션 계정에서는 기존 접근통제·승인 절차를 적용하세요. 별도 실운영 환경에서 `terraform apply`를 자동 호출하도록 구성하지 않았습니다.

## 5. GitHub Actions 보안

- 소스코드 분석/테스트 job은 `contents: read`로 실행하고, PR 결과 댓글은 **별도 job에서만 `pull-requests: write`** 권한을 받습니다. 댓글 job은 PR 코드를 checkout하거나 실행하지 않습니다.
- GitHub 외부 Fork PR에 댓글 쓰기나 AWS 권한을 허용하지 않습니다.
- AI API 호출은 별도 동의를 받은 **수동 workflow_dispatch**에서만 활성화되고, 원본 소스/파일명/함수명은 전송하지 않습니다.
- AWS 가격 API는 기본 비활성화이며, 별도의 임시 IAM 인증 없이는 계정 접근이 되지 않습니다.
- 타 저장소에서 Action을 사용할 때는 `@main` 대신 검증된 커밋 SHA로 고정하고, 서드파티 Actions/의존성의 버전과 공급망 이슈를 검토하세요.
- `terraform-plan.json`은 **절대 PR이나 Git 커밋을 통해 주입하지 않는 방식**을 권장합니다. 현 Action 입력은 실행 중 생성한 비밀 관리 파일 경로만 전달하는 데 사용해야 합니다.

## 6. 정기 운영·유지보수 체크

| 주기 | 점검 | 조치 |
| --- | --- | --- |
| 매 PR | Python·JS AST·보안 규칙 테스트, Actions 권한 | 실패 시 병합 금지; 근거 부족은 검토 필요로 유지 |
| 매주 | Actions 실패·의존성 보안 취약점·새로운 Terraform 패턴 | 경고/실패 원인 확인, 이슈 등록 |
| 매월 | AWS Price List 단가 기준일, 지역·사용량·예산, OpenAI/AWS API 사용 비용 | 시나리오 재산정, 비용 드리프트 기록 |
| 분기 | Python/Node/Graphviz/Diagrams/boto3 의존성 업데이트, IAM 권한, OIDC 신뢰 정책 | 버전 고정 업데이트 → 회귀 테스트 → 승인 |
| 배포·요구사항 변경 시 | 새로운 API·DB·SLO·민감 데이터와 설계 구성 변화 | 사용자 승인된 ADR 업데이트 및 검증 재수행 |

운영 단계에서 추천 관리 지표: `analysis_success_rate`, `unpriced_line_count`, `critical_iac_finding_count`, `manual_review_count`, `architecture_change_review_time`. 단순히 규칙 통과 비율을 **보안 점수**로 사용하지 마세요.

## 7. 다음 단계 및 미완료

- 실제 AWS 공식 가격 데이터와 다양한 AWS 서비스 SKU별 계층 요금·청구 금액 교차검증 (현재 단일 무조건 온디맨드 가격만 지원).
- Terraform HCL/CDK/CloudFormation 소스 전반의 정책 검증 및 Checkov 같은 전문 검사기와 연계.
- 변경된 PR에 대한 비동기 분석, 권한 있는 사용자 승인, 비용 경보, 검증 이력 보존 정책.
- 실제 AWS 구성·보안·부하/장애 복구 테스트 결과를 별도 증거로 확보한 뒤 운영 적합성 평가.

참고: [AWS Price List Query API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html), [GetProducts](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_pricing_GetProducts.html), [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [Checkov Terraform 검사](https://www.checkov.io/7.Scan%20Examples/Terraform.html).
