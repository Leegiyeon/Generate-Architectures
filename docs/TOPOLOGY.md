# AWS To-Be 상세 토폴로지 (Issue #11 기반 구현)

> 이 결과는 **AWS 계정에 배포된 인프라가 아니라 구조화된 참조 설계 후보**입니다. 실제 CIDR·라우팅 테이블·IAM·보안그룹 설정과 RDS/AZ 구성은 조회하거나 생성하지 않습니다. 건축 설계의 기초 도면이며 배포 명세서가 아닙니다.

## 사용자에게 새로 제공되는 것

기존 `architecture.svg/png`(AWS 아이콘이 포함된 간결한 서비스 참조도)은 유지합니다. 추가로 `aws-topology.json`, `aws-topology.md`, `aws-topology.svg/png/dot`를 생성합니다.

- **JSON**: 영역(AWS Cloud → VPC → 논리 AZ → Public/Private App/DB Subnet), 서비스·스토리지·관계의 **계층 구조**, 선정 근거 ID, 통신 경계 및 미확정 항목.
- **SVG/PNG/DOT**: 영역별 논리 토폴로지와 제안한 연결선. 기존 AWS 아이콘 그림과 구분되어 **네트워크 영역을 설명**합니다.
- **Markdown**: 제안된 서비스/영역, 데이터 흐름과 구축 전에 확인해야 할 NAT·보안그룹·DB·가용성·리전 정보.

## 참조 패턴의 기본 논리

| 패턴 | 현재 제안하는 토폴로지 | 중요한 검증 전제 |
| --- | --- | --- |
| Static | Client → CloudFront → 비공개 S3 + OAC / WAF 후보 | CloudFront 오리진이 S3 웹사이트 엔드포인트가 아니라 일반 S3 버킷인지, OAC 버킷 정책·인증서·도메인 |
| Serverless API | Client → API Gateway → Lambda → DynamoDB(사용이 확인된 경우에만) | Lambda에 VPC를 **무조건 추가하지 않음**, 실행시간·동시 실행·DynamoDB 데이터 모델 |
| Mobile | Client + Cognito(사용자 요구 시) → API Gateway → Lambda | 인증 제공자 변경 필요 여부, 실제 DB/영속성 요구 |
| Container API | 2개 논리 AZ의 Public/Private App 서브넷, 인터넷용 ALB, ECS Fargate | ALB 대상그룹/SG/포트·ACM, private ECS 이미지 pull을 위한 NAT 또는 필요한 VPC Endpoint, AZ 장애 대응 |
| Container + RDS | 위 Container 패턴에 DB Subnet Group(2 AZ) + RDS Primary, HA 요구 시 Standby | RDS 엔진/백업/암호화/DB SG, Multi-AZ 용량·비용·장애 복구 검증 |

**RDS DB subnet group은 단일 AZ DB 인스턴스라도 일반적으로 두 개 이상의 AZ 서브넷을 포함**하도록 제안합니다. Multi-AZ DB Instance의 standby는 읽기 확장용 복제본이라고 표시하지 않습니다. HA 요구사항이 없는 개발 환경에서는 ECS 작업을 두 AZ에 실제 배포했다고 주장하지 않습니다.

**AWS 참고 문서**
- [Create an Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-application-load-balancer.html) — ALB용 서로 다른 AZ의 서브넷.
- [ECS Fargate task networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html) — Fargate private subnet에서 ECR·외부 연결을 위한 NAT 또는 VPC Endpoint.
- [RDS DB subnet group](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html) — DB subnet group 및 Multi-AZ.
- [CloudFront OAC S3 origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) — 비공개 S3 오리진 OAC.

## 설계 모델과 근거의 구분

- 모든 `nodes`의 상태는 `proposed_not_deployed`이며, 모든 `edges`는 `proposed_not_verified`입니다.
- `evidence_ids`는 사용자가 **명시한 요구사항**(R…) 또는 정적 분석 단서(F…)만 참조합니다. 아무 근거 ID가 없는 구성은 **AWS 참조 설계 제안**이지 코드에서 관측한 기존 리소스가 아닙니다.
- `symbolic_azs: [AZ-A, AZ-B]`는 설명용 논리 AZ를 뜻합니다. 실제 `ap-northeast-2a` 같은 AZ 이름이나 계정별 물리 AZ ID를 임의 지정하지 않습니다.
- `high_availability_proposed`는 목표 가용성 99.9% 이상, 운영 환경 또는 고가용성 선호 시 두 AZ에 작업 배치를 **제안**하는 것이며 실제 SLO 달성 판정은 아닙니다.
- `review_required`는 NAT/VPC Endpoint, IAM, SG, 라우팅, AZ/리전, 인증서, 트래픽/용량, RDS 엔진·Multi-AZ 비용 등을 사용자에게 확인하도록 요구합니다.
- 정적 분석 일부가 실패하면 `NET-EVIDENCE-PARTIAL`을 남깁니다.

## 보안 및 정확성 원칙

아키텍처 설계 단계에서 다음 항목은 **확인 없이 결정하지 않습니다**: 실제 IP 주소/CIDR 범위, AWS 실제 리소스 ID, IAM 자격증명, SSH/RDP 공개 여부, NAT Gateway 생성 수량과 가격, Elastic IP, RDS 인스턴스 타입, 비밀키, 실제 오토스케일 설정 및 클라우드 계정 보안 통과 판정.

AWS 관련 API 호출이나 Terraform apply는 없습니다. 이 그래프는 별도 네트워크/운영 검증과 인간 승인 없이 실제 인프라 변경의 근거로 사용하지 않습니다.

## 남은 범위와 다음 단계

1. [기반 구현] 실제 AWS 서비스 아이콘과 상세 AZ/Subnet 영역을 **통합 다이어그램으로 연결**. 일부 네트워크 제어 항목은 텍스트 노드로 표시.
2. [기반 구현] 포트/SG 접근 범위·NAT·VPC Endpoint 선택에 대한 명시 입력과 규칙/미확인 표시. 실제 AWS 정책/라우트와의 대조는 미구현.
3. SSR/정적 백엔드 분리·문서형 DB/관계형 DB 엔진 판단과 타깃 프로젝트의 코드 흐름 연결.
4. AWS 공식 가이드와 견적·가용성 근거의 버전 관리, 10개 대표 프로젝트의 수동 리뷰.

상세 토폴로지 기반은 구현되었으나, 운영 계정의 배포 준비 완료나 검증된 최적 설계라고 표현하지 않습니다.


## 통합 AWS 아이콘 토폴로지 및 네트워크 의도 (Issue #11 후속)

\`aws-topology.svg/png\`은 이제 **VPC → 논리 AZ → Public/Private App/DB Subnet 경계 안에 지원되는 AWS 서비스 아이콘**을 그립니다. 이미지의 모든 서비스는 배포 확정이 아닌 **설계 후보**입니다. SVG에는 AWS 아이콘 이미지를 내장하여 GitHub Artifact 외부에서도 열 수 있습니다. IGW/NAT/Endpoint 등 전용 아이콘 매핑이 없는 항목은 명시적 레이블 상자로 표시됩니다. 기존 간결한 \`architecture.svg/png\`도 유지합니다.

설계 구조와 사용자 선택:
- **공개 ALB**(\`alb_scheme: internet_facing\`): Public Subnet 2개(AZ-A/B)와 IGW 제안, ALB→ECS 작업은 ALB SG만 허용하는 의도. ACM/TLS·Route Table·IGW 설정은 **미검증**입니다.
- **내부 ALB**(\`alb_scheme: internal\`): Private App Subnet 2개와 내부 DNS/내부 네트워크 접근 제안, 기본 IGW를 만들지 않습니다. VPC/전용망/VPN/TGW 연결은 사용자 확인 필요.
- **Private ECS outbound 미입력**: NAT/VPC Endpoint 중 무엇을 쓸지 **결정하지 않습니다**. \`NET-EGRESS-CHOICE\`로 표시합니다.
- **NAT 선택**(\`egress_strategy: nat_gateway\`): 기존 IGW 외에 단일 작업 AZ 또는 HA 선택 시 **AZ별 NAT**를 후보로 추가합니다. EIP, 비용, Route Table·외부 API 전송 범위는 미확정입니다.
- **VPC Endpoint 선택**(\`egress_strategy: vpc_endpoints_only\`): ECR API/DKR, S3 Gateway, CloudWatch Logs, 필요 시 Secrets Manager Endpoint 후보를 표시합니다. 실제 Private DNS·SG·AZ별 endpoint ENI·AWS 서비스 사용 현황은 미확정입니다.
- **외부 인터넷 API가 필수인 경우**, endpoint-only는 일반 인터넷 아웃바운드를 제공하지 않으므로 \`NET-EGRESS-CONFLICT\`로 설계 후보를 **차단 검토**합니다. NAT+Endpoint 전략(\`nat_plus_endpoints\`)도 선택 가능합니다.
- **보안그룹 의도**: Client→ALB TCP443(제안), ALB SG→ECS SG(\`container_port\` 명시 시만 포트 확정), ECS SG→RDS SG(\`database_port\` 명시 시만 포트 확정). **0.0.0.0/0 DB/SSH 공개 정책을 만들지 않습니다.**

요구사항 JSON에 추가할 수 있는 필드:

\`\`\`json
{
  "alb_scheme": "internet_facing",
  "egress_strategy": "undecided",
  "external_outbound_required": true,
  "container_port": 8080,
  "database_port": 5432
}
\`\`\`

이 예시의 숫자는 사용자 프로젝트의 실제 컨테이너·DB 포트가 아닙니다. 코드를 기반으로 포트를 추론해 확정하지 않으므로 **사용자가 확인해 입력**해야 합니다. 값을 지정하지 않았을 때 포트·EGRESS는 미확정으로 출력됩니다.

산출물 추가: \`network-policy.md\` — 제안된 SG 접근 범위, 미설정 Route Table 의도, 사용자가 확인해야 할 조건, 공식 AWS 근거 링크. \`aws-topology.json\`의 모든 노드와 연결선에는 **\`design_rule_ids\`**가 있고, 사용자 입력·코드 근거가 존재하는 경우에만 \`evidence_ids\`를 기록합니다. \`rule_catalog\`에는 규칙별 출처와 해석 제한이 포함됩니다.

**미구현·검증 필요**: 실측 트래픽 기반 Auto Scaling/개별 AWS SKU 비용, SG/Route Table 실제 생성/검증, 전체 IAM, 실제 부하·장애 테스트, 세부 SSR 분리 및 DB 엔진 선택. 후속 Issue #12(선정 근거), #13(보안·확장·운영)으로 이어집니다.
