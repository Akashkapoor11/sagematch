# Devpost draft

## Project name
SageMatch — Grounded Software Advisor

## Elevator pitch (under 200 chars)
From messy catalogue to defensible top-3 software picks: sanitize data, probe missing requirements, rank with hard constraints, and explain every recommendation with evidence.

## About the project
### The problem
Software catalogues are often inconsistent, while customer requests are incomplete and ambiguous. A recommendation system that guesses can produce plausible-sounding but irrelevant choices.

### Our approach
SageMatch treats recommendation as a grounded decision pipeline. First, it maps messy catalogue columns into a canonical schema, normalizes ranges/lists, detects duplicates, validates fields, and produces a data-quality report. The cleaned records are stored in PostgreSQL for reliable querying.

Next, a requirements layer extracts explicit constraints from a customer query. When key information is missing, the system asks a small number of high-impact questions instead of asking generic follow-ups.

Finally, a constraint-aware ranker combines category, team-size, integration, feature, deployment, pricing, and semantic evidence. Explicit must-have conflicts are penalized or gated. The top three results include concrete evidence for why they fit and explicit gaps that would improve the match.

### LLM usage
The engine supports an OpenAI-compatible/local LLM endpoint for requirement understanding and safe question phrasing. The recommendation facts remain grounded in the sanitized catalogue and ranking layer, so the LLM is not the source of product facts.

### What we learned
The key lesson is that recommendation quality starts before the model: a clean, well-structured catalogue and explicit constraints make downstream reasoning measurable, explainable, and safer.

### Built with
React, Vite, Python, FastAPI, PostgreSQL, Pydantic, HTTPX, optional OpenAI-compatible/local LLM

## Demo flow
1. Start with a vague request to show probing.
2. Enter a fully specified request to show top-3 ranking.
3. Open a result to show evidence and gaps.
4. Upload a messy catalogue to show sanitization and quality reporting.
