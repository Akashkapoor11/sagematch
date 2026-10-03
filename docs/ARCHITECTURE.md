# Architecture

```text
                  ┌──────────────────────────┐
                  │  CSV / JSON catalogue    │
                  └────────────┬─────────────┘
                               │
                       sanitize + validate
                               │
                  ┌────────────▼─────────────┐
                  │ Data Quality / Normalizer │
                  │ aliases · lists · ranges │
                  │ duplicates · issues      │
                  └────────────┬─────────────┘
                               │
                           PostgreSQL
                               │
Customer query ──► Requirements extractor ──► Missing-requirement probe
                                      │                    │
                                      └──── answers ◄──────┘
                                               │
                                   Constraint-aware ranker
                                               │
                                      ┌────────▼────────┐
                                      │ Top 3 products  │
                                      │ evidence + gaps │
                                      └─────────────────┘
```

## Design principles

**Grounding over generation:** recommendations are produced from normalized catalogue records.

**Hard constraints matter:** an explicit category/team-size/integration mismatch is penalized rather than buried by semantic similarity.

**Probing is selective:** questions target dimensions that can materially change the candidate set; the UI caps the initial round at three questions.

**Graceful degradation:** the system runs deterministically without an LLM and can be enhanced with an OpenAI-compatible/local endpoint when the hackathon key is available.


## Why this architecture is deliberately hybrid

The deterministic path is the system of record: catalogue facts come from sanitized records, hard constraints can gate candidates, and explanations cite the fields used by the ranker. An optional OpenAI-compatible/local LLM can improve language-level requirement extraction, but its output is constrained against the vocabulary actually present in the catalogue. This avoids a common failure mode in recommendation demos: fluent but unsupported product claims.

## Edge-case policy

When at least three products satisfy the explicit hard constraints, only compliant products can enter the top three. When fewer than three comply, the engine returns the best available fallbacks but clearly marks those cards as relaxed/non-compliant and exposes the violated evidence.

## Persistence — PostgreSQL

The application defaults to PostgreSQL through `DATABASE_URL` using SQLAlchemy + psycopg. The Docker Compose stack provisions PostgreSQL 16, waits for `pg_isready`, and then starts the API. Products are persisted in `products`; the latest data-quality report is persisted in `metadata`. SQLite is used only by the automated tests when no PostgreSQL server is available in the test environment.
