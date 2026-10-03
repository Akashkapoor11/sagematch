# SageMatch - Grounded Software Advisor


## The problem in one sentence

Software catalogues are inconsistent, customer queries are vague, and a recommendation engine that guesses produces fluent-sounding but irrelevant results.

## How SageMatch solves it

SageMatch treats recommendation as a **four-stage grounded decision pipeline**:

```
Messy CSV / JSON
      │
      ▼  ① Data sanitization
 Canonical product store (PostgreSQL)
      │
      ▼  ② Requirement extraction + probing
 Structured customer needs (+ clarifying questions if needed)
      │
      ▼  ③ Constraint-aware ranking
 Ordered candidate pool (hard constraints gated; strict before relaxed)
      │
      ▼  ④ Grounded explanation
 Top 3 recommendations with evidence, gaps, and score breakdown
```

Every stage is **deterministic by default**. An optional OpenAI-compatible LLM is called first at each stage and accepted only when its output passes schema validation against the actual catalogue vocabulary.

---

## Implementation map

| Criterion | What SageMatch does |
|-----------|---------------------|
| **Data quality** | Alias-based schema mapping for flexible column names; whitespace/case/unicode normalization; multi-delimiter list parsing (`,;|/and`); team-range text parsing (`10 to 50`, `20+`, `unlimited`); reversed-bounds repair; URL normalization and validation; cross-row deduplication; per-row rejection/repair counters; persisted quality score |
| **Recommendation logic** | Weighted evidence ranker across category (27%), integrations (21%), features (16%), team size (15%), deployment (12%), pricing (5%), semantic TF-IDF (4%); hard-constraint gating — strict pool of fully-compliant products filled first; relaxed fallbacks only when the catalogue cannot satisfy all constraints three times; exclusion penalty (0.08×) for forbidden integrations |
| **Probing quality** | Information-gain planner selects missing dimensions by entropy over the candidate pool; category is always first because it changes the search universe most; questions supply real catalogue options as choices; each question reports its expected decision impact; capped at 3 questions; fully-specified requests skip probing entirely |
| **Reasoning** | Every recommendation card shows: explicit matched requirements, unmet gaps, "Why it fits" bullets tied to catalogue evidence, "Improve the fit" gaps, per-dimension score breakdown, evidence rows with source CSV row number |
| **Engineering craft** | FastAPI + Pydantic v2 + SQLAlchemy 2 + PostgreSQL 16; React + Vite frontend; API-first LLM adapter (each stage independently validated with deterministic fallback); modular core (`data_pipeline`, `query_understanding`, `ranker`, `llm`); automated regression suite; Docker + Compose; CLI validator; Vercel-ready frontend |

---

## Quick start

```bash
# With Docker (recommended — starts PostgreSQL automatically)
docker compose up --build
# Open http://127.0.0.1:8000

# Without Docker (requires a running PostgreSQL instance)
pip install -r backend/requirements.txt
DATABASE_URL=postgresql+psycopg://... uvicorn backend.app.main:app --reload
```

### Enable the LLM adapter

```bash
cp .env.example .env
# Edit .env: set LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
docker compose up --build
```

The system runs fully deterministically without an LLM key. Add a key to enable API-first requirement extraction, adaptive probing wording, compliant candidate reranking, and grounded explanation generation.

---

## Verification

```bash
make test        # 111 tests — no Docker required (uses an isolated test DB)
python backend/scripts/validate_catalog.py sample/messy_catalog.csv    # Sanitize the demo catalogue; print the quality report
python backend/scripts/evaluate_queries.py sample/demo_queries.json    # Run 8 demo queries; print ranked results + constraint analysis
make check       # Backend tests + React build + catalog validation + demo evaluation
```

---

## API-first LLM policy

Every LLM-assisted stage follows the same contract:

1. **Call the configured API first** — never the deterministic fallback.
2. **Validate the response** against the catalogue vocabulary and explicit query signals. If the model omits an integration you mentioned, the response is rejected.
3. **Fall back immediately** on any transport error, timeout, invalid JSON, or schema violation.
4. **Never let the model invent facts.** Products come from the sanitized catalogue. Explanations cite only evidence already produced by the ranker. The reranker receives a grounded pool and must return every ID exactly once.

The response trace (`api_trace`) exposes which mode each stage used, so judges can verify this policy at runtime.

---

## Architecture

```
Browser (React + Vite)
    │ REST
    ▼
FastAPI  (/api/query, /api/catalog/upload, /api/health)
    │
    ├── data_pipeline.py  — sanitize & ingest CSV/JSON → Product[]
    ├── query_understanding.py — parse requirements; probe missing dimensions
    ├── ranker.py  — score + rank products; produce EvidenceItem[]
    ├── llm.py  — API-first adapter (understand / probe / rerank / explain)
    └── db.py  — SQLAlchemy ORM → PostgreSQL 16
```

---

## File structure

```text
sagematch_/
├── frontend/                    # React + Vite UI
│   ├── src/
│   │   ├── App.jsx              # Main React component
│   │   ├── App.test.jsx         # Vitest smoke test
│   │   ├── api.js               # Fetch wrapper
│   │   ├── main.jsx             # React entry point
│   │   └── styles.css           # Dark-theme design system
│   ├── index.html
│   ├── package.json
│   ├── README.md
│   ├── vite.config.js
│   └── vercel.json
├── backend/                     # FastAPI + PostgreSQL backend
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── data_pipeline.py
│   │   │   ├── db.py
│   │   │   ├── llm.py
│   │   │   ├── models.py
│   │   │   ├── query_understanding.py
│   │   │   └── ranker.py
│   │   └── main.py
│   ├── scripts/
│   │   ├── evaluate_queries.py
│   │   └── validate_catalog.py
│   ├── tests/                   # 10 test files — 111 automated tests
│   │   ├── conftest.py
│   │   ├── test_api.py
│   │   ├── test_llm_fallback.py
│   │   ├── test_pipeline.py
│   │   ├── test_pipeline_extended.py
│   │   ├── test_probing.py
│   │   ├── test_probing_extended.py
│   │   ├── test_ranker_extended.py
│   │   ├── test_recommender.py
│   │   └── test_robustness.py
│   ├── data/                    # Runtime data; DB files git/ZIP ignored
│   ├── requirements.txt
│   └── pyproject.toml
├── sample/                      # Demo catalogue + guideline + queries
│   ├── demo_queries.json
│   ├── messy_catalog.csv
│   └── product_data_guideline.md
├── docs/                        # Architecture, API-first, demo, judging docs
│   ├── API_FIRST.md
│   ├── ARCHITECTURE.md
│   ├── DEMO_SCRIPT.md
│   ├── DEVPOST_COPY.md
│   ├── JUDGING_MAP.md
│   ├── REASONING.md
│   └── SUBMISSION_CHECKLIST.md
├── data/                        # Runtime data location; DB files are git/ZIP ignored
│   └── .gitkeep
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── FINAL_AUDIT.md
├── LICENSE
├── Makefile
├── README.md
├── run.ps1
└── run.sh
