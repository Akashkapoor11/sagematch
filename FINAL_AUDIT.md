# SageMatch Release Audit

## Release target

Clean production layout for the Zoftware Hireathon: React/Vite frontend, FastAPI backend, and PostgreSQL data layer.

## Exact release verification

- Backend automated suite: **111/111 PASS**.
- Python AST parsing and compilation across all backend Python modules: PASS.
- JavaScript/JSX syntax parsing across all frontend JS/JSX files: PASS.
- JSON/YAML configuration parsing: PASS.
- Bash script syntax (`run.sh`): PASS. PowerShell script (`run.ps1`): PASS.
- Full release-text scan: no trailing whitespace, control characters, private-key markers, hard-coded API-key patterns, stale artifact references, or stale metric claims.
- Production/default database: PostgreSQL through `DATABASE_URL` using SQLAlchemy + psycopg.
- Frontend: React + Vite under `frontend/`.
- Backend: FastAPI under `backend/`.
- Docker Compose: PostgreSQL 16 health-checked before the API starts.
- Dockerfile: React build is produced first and copied into the API image.
- FastAPI serves the Vite asset prefix at `/assets/` and the built frontend bundle from the same production image.
- `assets_dir` in `main.py` correctly uses `static_dir / 'assets'` (not raw `frontend_dist`).
- Vercel configuration uses the Vite build/output settings without a catch-all rewrite that would intercept `/assets/*`.
- API-first LLM policy: configured API is attempted first at each LLM-assisted stage; invalid/failed responses trigger deterministic fallback.
- Pricing-tier contract validation: active. Dead `if False:` block removed; `allowed_pricing_set` built from the real `allowed_pricing` parameter passed to `understand()`.
- Reranker contract: only supplied candidate IDs can be returned; the ordering must contain every supplied ID exactly once; strict hard-constraint candidates retain precedence.
- Explanation contract: explanations are accepted only when grounded in supplied recommendation evidence.
- Evidence provenance: recommendation evidence carries the originating catalogue `source_row`.
- `budget_text` field rendered in `requirementTags` in `App.jsx`.
- `trace-toggle` button carries `id="trace-toggle-btn"` for browser-test automation.
- `.gitignore` and `.dockerignore` both exclude `node_modules/` and `frontend/dist/`.
- `pytest-asyncio==0.24.0` added to `requirements.txt`; `asyncio_mode = "auto"` set in `pyproject.toml`.
- Demo catalogue evaluation: 39 input rows → 34 sanitized products, 3 duplicates removed, post-sanitization health **100.0/100**.
- Demo evaluation: **8 queries**, **0 hard-constraint violations**, **2 probing cases**.
- Clean-room HTTP smoke: root frontend, `/assets/*`, health, stats, quality, products, demo-cases, complete query, and probing query all passed under the isolated test database.
- Clean-room OpenAI-compatible HTTP smoke: live local mock endpoint accepted by the API-first LLM client.
- Release archive excludes runtime databases, Python caches, npm artifacts, and environment secrets.

## Final source audit scope

The release tree contains **62 text/source files** and was scanned line-by-line before packaging. The audit included source code, tests, configuration, deployment files, documentation, sample data, and frontend assets.

| Category | Files |
|---|---|
| Backend core | `main.py`, `config.py`, `data_pipeline.py`, `db.py`, `llm.py`, `models.py`, `query_understanding.py`, `ranker.py` |
| Backend tests | `conftest.py`, `test_api.py`, `test_llm_fallback.py`, `test_pipeline.py`, `test_pipeline_extended.py`, `test_probing.py`, `test_probing_extended.py`, `test_ranker_extended.py`, `test_recommender.py`, `test_robustness.py` |
| Backend scripts | `validate_catalog.py`, `evaluate_queries.py` |
| Frontend | `App.jsx`, `App.test.jsx`, `api.js`, `main.jsx`, `styles.css`, `index.html` |
| Config | `package.json`, `vite.config.js`, `vercel.json`, `pyproject.toml`, `requirements.txt` |
| Deployment | `Dockerfile`, `docker-compose.yml`, `Makefile`, `run.sh`, `run.ps1`, `.env.example`, `.gitignore`, `.dockerignore` |
| Docs | `README.md`, `FINAL_AUDIT.md`, `ARCHITECTURE.md`, `API_FIRST.md`, `DEMO_SCRIPT.md`, `DEVPOST_COPY.md`, `JUDGING_MAP.md`, `REASONING.md`, `SUBMISSION_CHECKLIST.md`, `frontend/README.md` |
| Sample | `messy_catalog.csv`, `demo_queries.json`, `product_data_guideline.md` |

## Environment limitations

This environment cannot reach the npm registry, so a fresh `npm install`/Vite production build could not be executed here. The React/JSX sources were syntax-parsed, the package manifest and Vite/Vercel configuration were validated, and the built-asset serving path was exercised with a clean-room Vite-like bundle. Docker is also unavailable here, so the Docker image itself could not be built; the Dockerfile/Compose configuration was parsed and cross-checked.

The official organizer catalogue and product-data guideline are supplied at kickoff and are not bundled here. The included catalogue/guideline are demo stand-ins and must be replaced/uploaded before final judging.
