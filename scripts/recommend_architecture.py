import argparse
import json
import os
from pathlib import Path

SKIP = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv", "__pycache__", "coverage", "vendor"}
SIGNALS = {
 "package.json": ("Node.js", "web"), "next.config.js": ("Next.js", "web"),
 "next.config.mjs": ("Next.js", "web"), "next.config.ts": ("Next.js", "web"),
 "vite.config.ts": ("Vite", "web"), "requirements.txt": ("Python", "backend"),
 "pyproject.toml": ("Python", "backend"), "go.mod": ("Go", "backend"),
 "pom.xml": ("Java", "backend"), "Dockerfile": ("Docker", "containers"),
 "docker-compose.yml": ("Docker Compose", "containers"),
 "compose.yaml": ("Docker Compose", "containers"),
 "serverless.yml": ("Serverless", "serverless"),
 "app.json": ("Expo", "mobile"), "pubspec.yaml": ("Flutter", "mobile"),
 "main.tf": ("Terraform", "infra")
}
def scan(root):
    found = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith("."))
        for name in files:
            if name in SIGNALS:
                technology, category = SIGNALS[name]
                found.append({"path": str((Path(current) / name).relative_to(root)), "technology": technology, "category": category})
                if len(found) >= 200:
                    return found
    return found

def design(found, kind, budget):
    categories = {f["category"] for f in found}
    technology = {f["technology"] for f in found}
    if kind == "auto":
        kind = "mobile" if "mobile" in categories else "web" if "web" in categories else "backend"
    if kind == "mobile":
        nodes = ["Mobile App", "Amazon Cognito", "API Gateway", "Lambda", "DynamoDB", "CloudWatch"]
        edges = [("Mobile App","Amazon Cognito"),("Mobile App","API Gateway"),("API Gateway","Lambda"),("Lambda","DynamoDB"),("Lambda","CloudWatch")]
        pattern = "Mobile backend"
    elif kind == "web" and ("Next.js" in technology or "Vite" in technology):
        nodes = ["User", "Route 53", "CloudFront", "S3", "AWS WAF", "CloudWatch"]
        edges = [("User","Route 53"),("Route 53","CloudFront"),("CloudFront","S3"),("AWS WAF","CloudFront"),("CloudFront","CloudWatch")]
        pattern = "Static web (validate SSR requirements)"
    elif "serverless" in categories or (kind == "backend" and "containers" not in categories):
        nodes = ["Client", "API Gateway", "Lambda", "DynamoDB", "CloudWatch"]
        edges = [("Client","API Gateway"),("API Gateway","Lambda"),("Lambda","DynamoDB"),("Lambda","CloudWatch")]
        pattern = "Serverless API"
    else:
        nodes = ["User", "Route 53", "AWS WAF", "Application Load Balancer", "ECS Fargate", "Amazon RDS", "CloudWatch"]
        edges = [("User","Route 53"),("Route 53","Application Load Balancer"),("AWS WAF","Application Load Balancer"),("Application Load Balancer","ECS Fargate"),("ECS Fargate","Amazon RDS"),("ECS Fargate","CloudWatch")]
        pattern = "Container web application"
    return {"workload":kind,"pattern":pattern,"input_budget_usd_month":budget,
            "detected_technologies":sorted(technology),"evidence":found,"nodes":nodes,"edges":edges,
            "limitations":["Conceptual reference design only: no AWS provisioning.",
                           "Manifest-based heuristics do not verify runtime workload or resource needs.",
                           "Input budget is not an AWS pricing estimate; validate cost, security and availability separately."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",default=".")
    p.add_argument("--output",default="architecture-output")
    p.add_argument("--workload",choices=["auto","web","backend","mobile"],default="auto")
    p.add_argument("--budget",type=float)
    args=p.parse_args()
    root=Path(args.repo).resolve()
    if not root.is_dir(): p.error("Repository must be a directory")
    if args.budget is not None and not (0 <= args.budget <= 10000000): p.error("Budget out of range")
    out=Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    result=design(scan(root),args.workload,args.budget)
    (out/"architecture.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    evidence="\n".join("- "+e["path"]+": "+e["technology"] for e in result["evidence"]) or "- No supported manifests found"
    report="# AWS Architecture Recommendation\n\nPattern: "+result["pattern"]+"\n\nDetected stack: "+(", ".join(result["detected_technologies"]) or "unknown")+"\n\n"
    report+="Budget input: "+(str(args.budget)+" USD/month" if args.budget is not None else "not provided")+" (not a price quote)\n\n## Evidence\n"+evidence+"\n\n## Limitations\n"
    report+="\n".join("- "+x for x in result["limitations"])+"\n\nSee architecture.svg (self-contained service icons), architecture.png, architecture.dot and architecture.json.\nSolid arrows show request/data flows; dashed lines show security associations and dotted lines show telemetry.\n"
    (out/"recommendation.md").write_text(report,encoding="utf-8")
    # Service-branded icon rendering with grouped AWS architecture boundaries.
    # Import here to let the metadata-only analyzer run independently in unit tests.
    from render_aws_icons import render_icon_diagram
    render_icon_diagram(result, out)
    print(report)

if __name__=="__main__":
    main()
