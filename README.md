# FinServ Global Compliance Copilot — Prototype

A runnable prototype of the **FinServ Global Regulatory Compliance Copilot** described in
[`system_prompt.md`](system_prompt.md). It implements all four playbooks from that system
prompt against a small, entirely **synthetic** regulatory corpus (RBI, Basel III, MiFID II),
so you can click through the actual behaviors the prompt specifies — cited answers, risk-rated
transaction screening, regulatory change impact analysis, and audit-ready report generation —
without needing access to any real regulatory database or production system.

> ⚠️ **Everything in `app/data/*.json` is fabricated.** Clause numbers, section titles,
> thresholds, effective dates, transactions, and policies are invented for this demo. None of
> it is real regulatory guidance. Every screen in the UI repeats this disclaimer.

## Why it's built this way

The system prompt's non-negotiable constraints (Section 1) are: **traceability first**, **no
silent guessing**, and **decision-support only, never a final determination**. To make those
constraints *verifiable* rather than just asserted by an LLM, the citation lookup, risk-rating
logic, and escalation rules are implemented as plain, auditable Python
(`app/services/{retrieval,qa,screening,impact,report}.py`) — not as free-form LLM output. You
can read exactly why any rating or citation was produced.

An LLM is used only as an **optional narration layer** on top of that deterministic logic:
if you set `ANTHROPIC_API_KEY`, the Q&A "direct answer" is phrased by Claude — using this
project's own `system_prompt.md` as the model's system prompt — but the model is only allowed
to restate the citations already retrieved by the engine, never to introduce new ones. Without
a key, a template produces the same structure so the whole app runs fully offline.

## Design docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): production design (scale, failure handling,
  regulation change, model deprecation, cost, residency) and which parts the prototype implements.
- [docs/TRADE_OFFS.md](docs/TRADE_OFFS.md): "why this over that" for model, vector store, framework,
  hosting and audit decisions, with the trigger to revisit each.

## What makes this a slice of the real system

| Concern | Where it lives | Tested in |
|---|---|---|
| Config-driven rules (thresholds, severities, retrieval and impact parameters) | `config/screening_rules.json`, `app/rules.py` | `test_time_and_config.py` |
| Point-in-time answers (`as_of`), supersession-aware retrieval | `app/services/retrieval.py` | `test_time_and_config.py` |
| LLM resilience: timeout, model fallback chain, circuit breaker, token budget, cache | `app/services/llm.py` | `test_llm_resilience.py` |
| Groundedness guardrail on LLM output | `app/services/guardrails.py` | `test_llm_resilience.py` |
| Tamper-evident audit trail, fail-closed | `app/audit.py` | `test_audit.py` |
| Liveness, readiness, request ids, latency headers | `app/routers/ops.py`, `app/main.py` | `test_time_and_config.py` |
| Langfuse tracing: per-decision traces, per-model-attempt generations, guardrail spans, quality scores, masking | `app/observability.py` | `test_observability.py` |

### Configuration

Environment variables (see `.env.example`); all optional.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Enables LLM narration; without it templates are used |
| `COPILOT_MODEL` | `claude-sonnet-5` | Primary model id |
| `COPILOT_LLM_FALLBACK_MODELS` | `claude-haiku-4-5-20251001` | Comma-separated fallback chain |
| `COPILOT_LLM_TIMEOUT_S` / `COPILOT_LLM_MAX_RETRIES` | `8` / `1` | Per-call limits |
| `COPILOT_LLM_BREAKER_FAILURES` / `COPILOT_LLM_BREAKER_COOLDOWN_S` | `3` / `60` | Circuit breaker |
| `COPILOT_LLM_DAILY_TOKEN_BUDGET` | `200000` | Cost ceiling; over budget degrades to templates |
| `COPILOT_AUDIT_LOG` | `var/audit.jsonl` | Audit log location |
| `COPILOT_AUDIT_FAIL_CLOSED` | `true` | Withhold decisions if the audit write fails |
| `COPILOT_REGION` | `local` | Cell identifier stamped on audit records |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | unset | Enables Langfuse tracing; unset means tracing is a silent no-op |
| `LANGFUSE_HOST` | Langfuse default | Point at a Langfuse instance in your region (self-hosted) for residency |
| `COPILOT_LANGFUSE_SAMPLE_RATE` | `1.0` | Fraction of traces exported |
| `COPILOT_OBS_CAPTURE_CONTENT` | `false` | `true` exports questions and model prompts/outputs; transaction payloads are never exported |
| `COPILOT_ENV` | `development` | Environment label shown in Langfuse |

Screening thresholds and severities are edited in `config/screening_rules.json` (validated on load,
version stamped on every result).

### Turning on Langfuse tracing

1. Get a Langfuse project: either a Langfuse Cloud project, or run Langfuse yourself (see the Langfuse
   self-hosting docs; for a regulated deployment host it in the same region as the cell).
2. In the project settings create an API key pair and put them in `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://your-langfuse-host
   ```
3. Restart the app. `GET /api/ready` now shows `observability.enabled: true`.
4. Use the app, then open Langfuse > Traces. Each Q&A, screening, impact and report call is a trace;
   Q&A traces show `retrieval`, `llm.narrate` (one generation per model attempt) and
   `guardrail.groundedness`, with scores such as `groundedness` and `retrieval_top_confidence`.
5. Switch the persona to Internal Auditor: results show the trace id, and the audit log
   (`GET /api/audit`) stores the same id for cross-reference.

Without keys nothing is imported or exported. Transaction payloads are never sent; questions and model
text are sent only when `COPILOT_OBS_CAPTURE_CONTENT=true`.

### Operational endpoints

`GET /api/health` (liveness), `GET /api/ready` (corpus, rules, audit log, LLM stats),
`GET /api/audit?limit=20`, `GET /api/audit/verify` (re-computes the hash chain).
Every response carries `X-Request-ID` and `X-Response-Time-ms`; the request id is stored in the audit record.

## Project structure

```
finserv-compliance-copilot/
├── system_prompt.md          # the source system prompt (also used as the LLM system message)
├── app/
│   ├── main.py                # FastAPI app, request-id/latency middleware, static frontend
│   ├── config.py               # environment-driven settings
│   ├── rules.py                # loads config/screening_rules.json
│   ├── audit.py                # hash-chained audit log
│   ├── routers/ops.py          # health, readiness, audit endpoints
│   ├── schemas.py               # pydantic request/response models
│   ├── data/                    # synthetic corpus + loader
│   │   ├── regulatory_corpus.json   # ~18 versioned RBI / Basel III / MiFID II clauses
│   │   ├── policies.json            # internal policy library (for impact analysis)
│   │   ├── transactions.json        # 8 sample transactions covering §5.2's scenarios
│   │   ├── circulars.json           # 2 old-vs-new circular pairs (for impact analysis)
│   │   └── prior_period.json        # synthetic baseline for report trend deltas
│   ├── services/
│   │   ├── retrieval.py          # keyword/topic-overlap "RAG" over the corpus
│   │   ├── qa.py                 # §5.1 Natural-language regulatory Q&A
│   │   ├── screening.py          # §5.2 Transaction screening (the rule engine)
│   │   ├── impact.py             # §5.3 Regulatory change impact analysis
│   │   ├── report.py             # §5.4 Compliance report generation
│   │   ├── llm.py                # Claude narration: timeout, fallback chain, breaker, budget, cache
│   │   └── guardrails.py         # rejects LLM output citing anything not retrieved
│   └── routers/copilot.py        # /api/* endpoints
├── config/screening_rules.json   # thresholds, severities, retrieval/impact parameters
├── docs/                         # ARCHITECTURE.md, TRADE_OFFS.md
├── run.py                        # `python run.py` entry point (e.g. Visual Studio startup file)
├── static/                       # vanilla HTML/CSS/JS frontend (no build step)
└── tests/                        # pytest coverage of the engine + API
```

## Running it

Requires Python 3.11+.

```bash
cd finserv-compliance-copilot
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000**. Everything runs offline — no API key required.

Opening the folder in VS Code and pressing **F5** runs the same thing via
[`.vscode/launch.json`](.vscode/launch.json) (uses `debugpy` + `uvicorn`, reads `.env`
automatically).

### Optional: enable real LLM narration

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Restart the server. The Q&A tab's "Direct answer" will now be phrased by Claude (grounded
strictly in the retrieved citations); the sidebar and report methodology section will say
`LLM narration: on`. If the call fails for any reason (no key, network, rate limit), every
code path falls straight back to the deterministic template — nothing breaks.

### Tests

```bash
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pytest
```

Tests exercise the rule engine directly (e.g. "unverified KYC + high-risk jurisdiction must
rate Critical and block", "the word 'approved' must never appear in a recommendation") and the
HTTP layer.

## Using the app

The sidebar has a **persona selector** (Compliance Officer / Compliance Head / Internal
Auditor) matching Section 4's persona table. The backend always computes the full, most-verbose
result; the persona selector controls how much of it the UI reveals by default — auditor sees
everything (full reasoning chain, raw inputs, audit-trail appendix), compliance head additionally
sees trend deltas, and the officer view stays terse. This is a simplification of Section 4's
three genuinely different response *shapes* — see **Known simplifications** below.

- **Regulatory Q&A** — ask a free-text question (try the example chips). Every answer shows a
  direct answer, the cited clauses with confidence/match-method, a version note (flags when a
  more recent amendment supersedes what was retrieved), and a jurisdiction note (flags when a
  question is ambiguous across IN/EU/US implementations of Basel III). An unanswerable question
  gets the exact "I could not locate a governing provision..." fallback from Section 3, not a
  guess.
- **Transaction Screening** — pick one of 8 sample transactions (or expand "Edit payload as
  JSON" to try your own) covering all four representative scenarios from Section 5.2: an
  unverified-KYC cross-border payment into a high-risk jurisdiction (Critical, blocks), an
  intra-group derivative breaching the large-exposure threshold (Basel III capital treatment),
  a cross-border NBFC/EU derivative (multi-framework), a retail structured-product sale with no
  appropriateness assessment (documentation gap, blocks — not a soft warning), and an NBFC
  priority-sector loan (reporting obligation). Every rating carries an explicit rationale list
  and reasoning chain — never a bare pass/fail, never "approved".
- **Regulatory Change Impact Analysis** — pick one of two synthetic circular amendments, see
  the old vs. new clause text side by side, the explicit change summary, and which internal
  policies match by keyword/topic overlap — including a separate list of below-threshold
  candidates that are flagged for human review rather than silently dropped.
- **Compliance Report Generation** — select a population of transactions and generate an
  executive summary, findings by framework, exceptions/escalations, a full per-transaction audit
  trail appendix (Internal Auditor view), and a methodology & limitations section that is never
  omitted or compressed, regardless of persona.
- **Regulatory Corpus** — browse the underlying synthetic clauses by framework/jurisdiction —
  this is the traceability substrate every other tab cites into.

## Mapping back to the system prompt

| System prompt section | Where it's implemented |
|---|---|
| §1 Traceability / no silent guessing / decision-support only | Every `CitationRef` carries doc/section/version/effective date; `qa.py`'s no-match template; `screening.py` never emits "approved"; `DISCLAIMER` constant |
| §2 Multi-framework detection | `screening.py`'s `frameworks` set + `multi_framework` flag; TXN-1003 fixture |
| §3 Grounding & retrieval, confidence, conflicts | `retrieval.py` (keyword/topic overlap, explicit method label, confidence floor) |
| §4 Persona-aware behavior | `personaSelect` + CSS `data-persona-min` gating in `static/app.js` / `style.css` |
| §5.1 Regulatory Q&A | `services/qa.py` |
| §5.2 Transaction Screening | `services/screening.py` |
| §5.3 Regulatory Change Impact Analysis | `services/impact.py` |
| §5.4 Compliance Report Generation | `services/report.py` |
| §6 Escalation & refusal rules | `screening.py`'s SAR-referral-not-filing note; `DISCLAIMER` |
| §7 Output hygiene | `as_of_date`/`engine_version` on every response; audit trail is never trimmed |

## Known simplifications (it's a prototype)

- **Retrieval is keyword/topic overlap, not a real embedding-based RAG pipeline.** That's
  explicitly labeled in every citation (`match_method`) rather than presented as verified
  semantic understanding, per Section 3 — but it's obviously less capable than production RAG.
- **Persona-aware "response shape" is approximated as cumulative reveal** (auditor ⊇ head ⊇
  officer) via CSS, not three genuinely distinct renderings. The real system prompt asks for
  three different *shapes*, not three depths of the same shape.
- **The synthetic corpus is small (~18 clauses, 8 transactions, 2 circulars)** — enough to
  exercise every playbook and every representative scenario in Section 5.2, not a real corpus.
- **No persistence.** Screening/report runs are computed on demand from the fixed JSON corpus;
  nothing is written back (a real deployment would log every AI-assisted decision for the audit
  trail requirement in Section 4's Internal Auditor row).
