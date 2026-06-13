# DevOps Reasoning Agent

A hackathon submission for the **Microsoft Agents League Hackathon** (Reasoning Agents track). This project uses an Azure AI Foundry agent powered by **o4-mini** to analyze GitHub Actions workflow failures through structured, multi-step reasoning — validated by a critic/verifier agent and backed by automated GitHub remediation.

Instead of scrolling through thousands of log lines, paste a failure log, fetch one from GitHub, or try a built-in demo failure. The agent classifies the error, locates the failure, explains the root cause, suggests a fix, and optionally opens a GitHub issue or a pull request that **directly patches the broken workflow file**.

## Architecture

![Architecture diagram](docs/architecture.svg)

## Highlights

- **4-step reasoning chain** (CLASSIFY → LOCATE → ROOT CAUSE → FIX) over a 20-type error taxonomy.
- **Critic/Verifier second pass** that approves or revises every analysis before any write action.
- **Real remediation:** the Fix PR commits a concrete patched workflow YAML to the actual `.github/workflows/*.yml` file — not just a note.
- **Demo-safe `DEMO_MODE`:** a deterministic, network-free analyzer guarantees the demo never hangs or fails on API latency.
- **Dogfooded in CI:** the agent is validated by a GitHub Actions pipeline that runs its own evaluator (`100%` taxonomy accuracy gate).
- **Responsible AI:** secret redaction before every model/GitHub call, plus explicit human approval for writes.

## 4-Step Reasoning

The agent follows a fixed reasoning chain for every log:

| Step | Name | Output |
|------|------|--------|
| 1 | **CLASSIFY** | Error category from 20-type taxonomy (e.g. `missing_file`, `test_failure`, `compile_error`) plus user-friendly subtype |
| 2 | **LOCATE** | Exact file, workflow step, and line number |
| 3 | **ROOT CAUSE** | Plain-language explanation of why the failure happened |
| 4 | **FIX** | Actionable remediation with a code or config snippet |

A **Verifier agent** then reviews the draft analysis and flags low-confidence or incorrect results before any GitHub action is taken.

Example structured output:

```json
{
  "error_type": "missing_file",
  "error_subtype": "package-lock.json not committed",
  "summary": "npm ci failed because the lockfile is missing from the repo.",
  "location": "Workflow step npm ci",
  "root_cause": "The lockfile was never committed to the repository.",
  "fix": "Run npm install locally and commit package-lock.json.",
  "confidence_score": 0.92
}
```

See [`error_types.py`](error_types.py) for the full 20-category taxonomy with user-friendly labels.

## Tech Stack

| Layer | Technology |
|-------|------------|
| AI Platform | Microsoft Azure AI Foundry |
| Model | o4-mini |
| LLM Client | `openai` AzureOpenAI SDK |
| Verifier | Second-pass Foundry agent (Critic/Verifier pattern) |
| Web UI | Streamlit |
| GitHub Integration | GitHub REST API (logs, issues, pull requests) |
| Safety | python-dotenv + secret redaction guardrails |
| Language | Python 3.9+ |

## Setup (5 Steps)

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd devops-reasoning-agent
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your Azure AI Foundry endpoint, API key, agent name, model, and GitHub token.

### 4. Verify the agent in Azure AI Foundry

Confirm your **DevOpsReasoningAgent** is deployed in Azure AI Foundry with the **o4-mini** model and that the endpoint matches `AZURE_ENDPOINT`.

### 5. Run the Streamlit app

```bash
streamlit run app.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`).

## Usage

1. **Paste Log** — Paste a GitHub Actions failure log and click **Analyze**.
2. **Fetch from GitHub** — Enter owner, repo, and run ID to pull logs automatically.
3. **Try Demo Failures** — One-click sample failures for instant demos.
4. **Review results** — See the 4-step analysis, verifier status, and parsed log context.
5. **Create GitHub Issue / Fix PR** — Approve the fix, then automate remediation. When you fetched a run from GitHub, the Fix PR commits a real patched workflow YAML (with a diff preview).
6. **Run Evaluation** — Score the agent against 15 built-in test cases in the sidebar.

See [DEMO.md](DEMO.md) for a 60-second judge demo script.

## Deploy to Streamlit Community Cloud

The app is deploy-ready — no code changes needed.

1. Push the repo to GitHub (already done; `.env` stays excluded via `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and **sign in with GitHub**.
3. Click **Create app → Deploy from GitHub**, then set:
   - **Repository:** `Chaitanya980/devops-reasoning-agent`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Open **Advanced settings → Secrets** and paste (TOML format):

   ```toml
   AZURE_ENDPOINT = "https://your-resource.services.ai.azure.com/api/projects/your-project"
   AZURE_API_KEY = "your-azure-api-key"
   AZURE_AGENT_ID = "DevOpsReasoningAgent"
   AZURE_MODEL = "o4-mini"
   AZURE_API_VERSION = "v1"
   GITHUB_TOKEN = "ghp_your_github_token"
   ```

   Streamlit Cloud exposes these as environment variables, which the app reads via `os.getenv(...)`.
5. Click **Deploy**. You'll get a public URL like `https://<your-app>.streamlit.app`.

**Demo-safe public deploy:** to host without exposing real Azure/GitHub keys, set a single secret instead and the app runs fully offline/deterministic:

```toml
DEMO_MODE = "1"
```

## Project Structure

```
devops-reasoning-agent/
├── error_types.py        # 20-category error taxonomy + labels/colors
├── agent.py              # Primary Foundry agent + orchestration + DEMO_MODE
├── offline_analyzer.py   # Deterministic, network-free fallback analyzer
├── verifier.py           # Critic/verifier second pass
├── guardrails.py         # Secret redaction + write validation
├── log_parser.py         # Log cleanup + context extraction
├── github_client.py      # Logs, issues, fix PRs (real workflow patches)
├── evaluator.py          # 15-case eval harness + report export
├── sample_logs.py        # Demo failure library
├── reasoning_ui.py       # Streamlit step components
├── app.py                # Main Streamlit app
├── tests/test_core.py    # Unit + integration tests (no network/secrets)
├── docs/architecture.svg # Architecture diagram
├── .github/workflows/ci.yml  # CI: tests + self-evaluation (dogfooding)
├── DEMO.md               # 60-second demo script
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

## Evaluation

The agent ships with a **15-case evaluation harness** covering the full error
taxonomy and four metrics. The table below is the reproducible **offline
deterministic baseline** (`DEMO_MODE=1`), which is also the gate enforced in CI:

| Metric | Score |
|--------|-------|
| Error-type accuracy | **100%** (15/15) |
| Location accuracy | 93.3% |
| Fix-quality accuracy | 60.0% |
| **Overall** | **93.3%** (14/15) |

> The live Azure o4-mini agent typically improves fix-quality further; the offline numbers are the deterministic floor used for regression testing.

Run the evaluator from Python:

```python
from agent import analyze_failure
from evaluator import run_evaluation

result = run_evaluation(analyze_failure)
print(f"Overall accuracy: {result['accuracy']}%")
print(f"Error type: {result['error_type_accuracy']}%")
print(f"Location: {result['location_accuracy']}%")
print(f"Fix quality: {result['fix_accuracy']}%")
```

Or click **Run Evaluation** in the Streamlit sidebar. Results are exported to `eval_report.json`.

Reproduce the offline baseline (no Azure key required):

```bash
DEMO_MODE=1 python -c "from agent import analyze_failure; from evaluator import run_evaluation; print(run_evaluation(analyze_failure))"
```

## Tests & CI

The project is dogfooded: a [GitHub Actions workflow](.github/workflows/ci.yml) runs the unit tests and the agent's own evaluator on every push.

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests are network- and secret-free — they exercise the pure helpers (`log_parser`, `guardrails`, `error_types`, JSON parsing) and the deterministic offline analyzer.

## Demo Mode (offline, no network)

Set `DEMO_MODE=1` to bypass Azure entirely and serve fast, deterministic
analyses from the built-in analyzer. This guarantees a reliable live demo and is
what the CI pipeline uses:

```bash
DEMO_MODE=1 streamlit run app.py
```

If Azure is reachable but a call fails, the agent automatically falls back to the
offline analyzer instead of erroring — the demo never hard-fails.

## GitHub Token Scopes

To use **Fetch from GitHub**, your token needs read access to Actions logs.

**Classic PAT:**
- `repo` — required for private repositories
- `workflow` — required to download Actions logs

**Fine-grained PAT** (on the target repository):
- Actions: Read
- Contents: Read (for workflow YAML context)
- Issues: Write and Pull requests: Write (only for Create Issue / Fix PR buttons)

## Finding the Run ID

1. Open your repository on GitHub
2. Go to **Actions**
3. Click the failed workflow run
4. Copy the number from the URL: `https://github.com/OWNER/REPO/actions/runs/123456789`

Use that number as **Run ID** in the app.

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| Fetch fails with 403 | Token missing scopes | Add `repo` + `workflow` scopes or fine-grained Actions: Read |
| Fetch fails with 404 | Wrong run ID or expired logs | Verify URL run ID; logs may expire after retention period |
| Invalid log archive | Redirect/auth issue | App now downloads logs without sending auth to blob URL |
| Wrong analysis after fetch | Demo log used instead of GitHub | Select **Fetch from GitHub** input source before Analyze |
| Run still in progress | Workflow not finished | Wait until the run status is completed |
| Verifier says needs review | Low confidence warning | Review output; warning no longer auto-rejects good results |

### CLI test for GitHub fetch

```bash
python -c "
from dotenv import load_dotenv
import os
from github_client import fetch_failed_job_logs
load_dotenv()
result = fetch_failed_job_logs('OWNER', 'REPO', 'RUN_ID', os.getenv('GITHUB_TOKEN'))
print('Failed jobs:', result['failed_job_names'])
print('Log chars:', len(result['log_text']))
print(result['log_text'][:500])
"
```

## License

MIT
