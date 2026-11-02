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
python3 -m unittest discover -s tests -v
python3 scripts/recommend_architecture.py --repo . --output architecture-output
```

## Outputs and boundaries
- `architecture.svg` / `architecture.png`: conceptual architecture diagram
- `architecture.dot`: Graphviz source
- `architecture.json`: detected evidence, components and assumptions
- `recommendation.md`: concise rationale, evidence and limits

No project source contents are sent to OpenAI or any model. Filesystem filename-based detection is deliberately limited; validate feasibility, runtime, networking, security, data residency, availability and actual AWS costs before using a proposal in production.
