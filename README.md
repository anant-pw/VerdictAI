# ⚖️ VerdictAI

> LLM Evaluation Framework — Test AI outputs with AI judges.

VerdictAI is an autonomous LLM testing framework that evaluates model responses using heuristic assertions and an LLM-as-judge pipeline. Built for QA engineers who need structured, repeatable, and CI-ready evaluation of AI systems.

---

## Why VerdictAI?

Traditional pass/fail automation breaks on probabilistic LLM outputs. VerdictAI solves this by combining:
- **Heuristic assertions** — fast, deterministic checks (length, contains, format)
- **LLM-as-judge** — semantic scoring against expected behavior using Groq
- **Memory** — SQLite-backed run history for trend detection and regression alerts
- **CI gate** — GitHub Actions integration with per-test pytest reporting
- **Dashboard** — Streamlit UI for live result visualization

---

## Stack

| Layer | Technology |
|---|---|
| Test definitions | YAML |
| Assertions | Python (custom runner) |
| LLM Judge | Groq (`llama-3.1-8b-instant`) |
| Memory | SQLite |
| CI/CD | GitHub Actions |
| Dashboard | Streamlit + Plotly |

---

## Project Structure

```
verdictai/
├── tests/
│   ├── suites/
│   │   ├── hallucination.yaml
│   │   ├── safety.yaml
│   │   └── format.yaml
│   ├── test_eval.py          # pytest wrapper (CI)
│   └── test_judge.py         # unit tests for judge parser
├── runner/
│   ├── loader.py             # YAML loader
│   ├── assertions.py         # heuristic assertion engine
│   ├── runner.py             # orchestrator
│   ├── groq_model.py         # model under test
│   └── main.py               # CLI entry point
├── judge/
│   ├── groq_client.py        # Groq API client
│   └── llm_judge.py          # LLM-as-judge scoring
├── memory/
│   └── store.py              # SQLite read/write + trend detection
├── dashboard/
│   └── app.py                # Streamlit dashboard
├── .github/
│   └── workflows/
│       └── sentinel_ci.yml   # GitHub Actions CI gate
├── config.env                # API keys + model config (not committed)
└── requirements.txt
```

---

## Layers

### Layer 1 — YAML Test Cases
Define test cases in YAML with input, expected behavior, assertions, and judge threshold.

```yaml
- id: hal_001
  input: "Who invented the telephone?"
  expected_behavior: "Must attribute invention to Alexander Graham Bell."
  judge_threshold: 75
  assertions:
    - type: not_contains
      value: "Thomas Edison"
    - type: max_length
      value: 500
```

### Layer 2 — Heuristic Assertions
Fast pre-checks before the LLM judge runs. Supported types: `contains`, `not_contains`, `max_length`.

### Layer 3 — LLM-as-Judge
Groq scores each response 0–100 against `expected_behavior`. Returns score, verdict, and one-line reason. Judge uses `temperature=0` for deterministic scoring.

### Layer 4 — SQLite Memory
Every run is persisted — `test_id`, `verdict`, `score`, `reason`, `response`, `latency_ms`, `run_timestamp`, `suite_name`. Enables trend detection and consecutive failure tracking.

### Layer 5 — CI/CD Gate
GitHub Actions workflow with manual trigger. Each test case maps to a pytest test — GitHub UI shows per-test pass/fail. Exits `1` on any failure. SQLite DB uploaded as artifact post-run.

### Layer 6 — Streamlit Dashboard
Live visualization of run history. Shows summary cards, pass/fail trend bar chart, score trend line chart per test, filterable results table, and CSV export.

---

## Setup

### 1. Clone and install
```bash
git clone https://github.com/yourname/verdictai.git
cd verdictai
pip install -r requirements.txt
```

### 2. Configure
Create `config.env` in project root:
```
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant
SENTINEL_DB=memory/sentinel.db
```

### 3. Run a suite
```bash
python -m runner.main --suite tests/suites/hallucination.yaml
```

### 4. Run via pytest (CI mode)
```bash
python -m pytest tests/test_eval.py -v
```

### 5. Launch dashboard
```bash
streamlit run dashboard/app.py
```

---

## CI/CD — GitHub Actions

Trigger manually from **Actions → Sentinel Eval — Manual CI Gate → Run workflow**.

Add these secrets in **Settings → Secrets → Actions**:
- `GROQ_API_KEY`
- `GROQ_MODEL`

---

## Roadmap

- [x] YAML test case loader
- [x] Heuristic assertion engine
- [x] Groq LLM-as-judge (score 0–100)
- [x] SQLite memory + run history
- [x] GitHub Actions CI gate
- [x] Streamlit dashboard
- [x] Regression eval — flag score drops >10 vs last run
- [ ] Consecutive failure self-healing trigger
- [ ] Excel / CSV input loader
- [ ] Safety + RAG test suites
- [ ] Hosted Postgres (production)
- [ ] Password-protected dashboard

---

## Part of the Sentinel Series

| Project | Purpose |
|---|---|
| **Sentinel QA** | Autonomous test execution framework (Playwright + FastAPI) |
| **VerdictAI** | LLM evaluation and judge framework |

---

## Author

Built by Max — SDET/QA Architect @ BOLD Technologies.  
[LinkedIn](https://linkedin.com/in/yourprofile) · [GitHub](https://github.com/yourname)
