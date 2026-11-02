# Generate Architectures

A runnable, **review-only** AWS architecture recommender. The original workflow was a prototype (no observed Actions runs, deprecated upload-artifact v3, unbounded OpenAI inference from filenames and an unchecked diagram-generation path). The new implementation is deterministic and does not require an API key.

## Architecture Action
1. Checks out target repository.
2. Detects supported manifest filenames (Node, Next.js, Vite, Python, Go, Java, Docker, Expo, Flutter, Terraform).
3. Selects a conservative reference pattern and documents evidence and limitations.
4. Generates Graphviz SVG, PNG, DOT, JSON and Markdown.
5. Uploads an Actions artifact. The repository workflow also comments on same-repository PRs.

No AWS resources are created; costs, scale and security are **not verified**. Next.js SSR workloads require manual review before using the static hosting design.

### Run here
Actions > AWS Architecture Recommendation > Run workflow (after merging PR). Reports are downloadable from the workflow run.

### Use in other repositories
Copy **examples/aws-architecture.yml** to the target repository as **.github/workflows/aws-architecture.yml**. It checks out that repo, invokes the published composite Action and uploads the output. The Action reference points at `@main`, so **merge this PR before using the template**. For stronger supply-chain security, pin `uses:` to the verified commit SHA. The target default branch must match the pull_request branch filter.

### Self-hosted GitHub App (optional multi-repository trigger)
The `app/server.py` webhook server is a **deployable scaffold**, not an already registered/installed GitHub App. It handles signed `pull_request` events and dispatches the installed template workflow in selected repositories. It does not itself analyze code. Every target repo must contain **.github/workflows/aws-architecture.yml** on its default branch.

1. Register a GitHub App in GitHub Developer settings (name of your choice).
2. Repository permissions: **Actions: Read and write**, **Contents: Read-only**, **Pull requests: Read-only**, **Metadata: Read-only**. Subscribe to **Pull request** events.
3. Set Webhook URL to `https://YOUR_HOST/webhook`, create a long random webhook secret, download your App private key.
4. Deploy the container from repository root using `docker build -f app/Dockerfile -t architecture-github-app .`. Run it behind HTTPS with `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` and `GITHUB_WEBHOOK_SECRET` environment variables. Keep all three confidential; supply the PEM private key as an environment variable with newlines or escaped `\\n`.
5. Install the App on selected repositories and add the example workflow to each default branch.
6. Open a PR in a selected repository. A webhook with a valid signature triggers its `workflow_dispatch` workflow, which generates downloadable artifacts.

**Note:** If using both the example template's `pull_request` trigger and the App webhook, a PR may produce two runs. For App-driven mode, remove the template's `pull_request` trigger. For pure Actions mode, no GitHub App or server is necessary. Neither mode provisions AWS resources.

### Local quick start
Install Python 3.10+ and Graphviz (with `dot` on PATH), then run:

```bash
python3 -m pip install -r requirements-diagrams.txt
python3 -m unittest discover -s tests -v
python3 scripts/recommend_architecture.py --repo . --output architecture-output
```

## Outputs and boundaries
- `architecture.svg` / `architecture.png`: conceptual architecture diagram
- `architecture.dot`: Graphviz source
- `architecture.json`: detected evidence, components and assumptions
- `recommendation.md`: concise rationale, evidence and limits

No project source contents are sent to OpenAI or any model. Filesystem filename-based detection is deliberately limited; validate feasibility, runtime, networking, security, data residency, availability and actual AWS costs before using a proposal in production.

## Icon-based architecture rendering

The architecture diagram uses **real AWS service icons** from `diagrams==0.25.1` instead of Graphviz's default text-only boxes. Client devices use representative client icons. AWS resources are visually grouped by **delivery, compute, data, security, and observability**.

**Diagram conventions:** Blue solid arrows are application/data flows; gold dashed arrows denote proposed security associations; grey dotted arrows denote telemetry. The diagrams are conceptual recommendations only; no AWS resources or verified VPC/subnet topology is represented. The `architecture.svg` embeds icon images so the artifact is viewable standalone without access to the GitHub runner filesystem.

The generator exports `architecture.png`, `architecture.svg`, and `architecture.dot`. The DOT file is a Graphviz source that refers to icons from the installed Diagrams package; install the pinned dependency to render DOT on another machine. For sending a standalone diagram to a coworker, use the PNG or SVG.

The upstream Diagrams library bundles its own AWS artwork; icon styling may differ from the most recently released official AWS icon package. For the latest official artwork, compare against [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/).

**Smoke-test all four reference patterns:**
```bash
python3 -m pip install -r requirements-diagrams.txt
python3 -m unittest discover -s tests -v
```
