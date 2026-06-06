# DevOps Reasoning Agent — Demo Script

Use this 60–90 second script when presenting to hackathon judges.

## Before You Demo

1. Start the app: `streamlit run app.py`
2. Confirm `.env` is configured and the Foundry agent responds
3. Open the sidebar so judges can see the **Reasoning Chain** and **Evaluation** sections

## 60-Second Demo Flow

### 1. Intro (10 seconds)

> "This is the DevOps Reasoning Agent — it analyzes GitHub Actions failures using multi-step reasoning on Microsoft Azure AI Foundry with o4-mini."

### 2. Demo Failure (15 seconds)

1. Open the **Try Demo Failures** tab
2. Select **ENOENT file not found**
3. Click **Analyze**
4. Point to the status panel showing CLASSIFY → LOCATE → ROOT CAUSE → FIX

### 3. Show Results (20 seconds)

1. Expand the four step cards
2. Highlight the error badge and confidence score
3. Mention the **Verifier** badge — a second critic agent validates the analysis
4. Expand **Parsed Log Context** to show structured exit code and failing step extraction

### 4. Safety + Automation (10 seconds)

1. Check **I approve this fix**
2. Explain guardrails redact secrets before analysis
3. Mention **Create GitHub Issue** or **Create Fix PR** for automated remediation

### 5. Evaluation (10 seconds)

1. Click **Run Evaluation** in the sidebar
2. Show the accuracy bar chart across error type, location, and fix quality
3. Mention 10 built-in test cases and `eval_report.json` export

## Closing Line

> "We combine Foundry reasoning, a verifier agent, Responsible AI guardrails, and GitHub automation to turn CI failures into actionable fixes in seconds."

## Troubleshooting During Demo

| Problem | Fallback |
|---------|----------|
| Azure API slow | Use a pre-run analysis screenshot |
| GitHub write fails | Show issue/PR UI without clicking |
| Eval takes too long | Show previously saved `eval_report.json` |

## Optional Talking Points

- **Reasoning Agents track:** multi-step chain + critic/verifier pattern
- **Reliability:** secret redaction and human approval before writes
- **Accuracy:** log pre-processing extracts exit code, failing step, and error snippet
- **Creativity:** one-click fix PR with suggested workflow changes
