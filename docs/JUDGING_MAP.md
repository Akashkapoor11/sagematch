# Judging map

## Data quality
`backend/app/core/data_pipeline.py` contains canonical-column aliases, normalization, range/list parsing, URL handling, duplicate detection, rejection/repair reporting, and a persisted quality report.

## Recommendation logic
`backend/app/core/ranker.py` combines explicit constraints with semantic overlap and uses hard-constraint gating when the catalogue has enough eligible candidates.

## Probing quality
`backend/app/core/query_understanding.py` selects high-impact missing dimensions and caps the initial round at three questions. The UI explains why each question matters.

## Reasoning
Recommendation cards show concrete matched requirements and explicit unmet requirements rather than generic praise.

## Engineering craft
The system is modular, typed with Pydantic models, backed by PostgreSQL, exposes a small FastAPI API, supports an OpenAI-compatible/local LLM adapter, includes Docker support, tests, a CLI validator, and a smoke evaluation harness.
