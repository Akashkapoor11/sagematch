# API-first AI policy

SageMatch uses a strict API-first policy for every LLM-assisted stage that is needed for a request.

1. Requirements extraction calls the configured OpenAI-compatible API first.
2. Probing generation calls the API first when clarification is needed and the deterministic probe planner has identified candidate missing dimensions.
3. Candidate reranking calls the API first, but only over candidates already admitted by the grounded deterministic ranker.
4. Recommendation explanations call the API first using only catalogue evidence already produced by the ranker.
5. If an API call fails, times out, returns invalid JSON, or fails schema validation, that stage immediately uses its deterministic fallback.

The API cannot create products, catalogue facts, or unconstrained recommendations. This keeps the system grounded while still using the external/local LLM whenever it is available.

The runtime trace reports `api_trace` per stage so a judge can see whether a stage used the API, fell back, or was not needed.

## Reranking contract

The API receives a grounded candidate pool and must return every supplied candidate ID exactly once. A partial, duplicate, unknown, or malformed ordering is rejected and the deterministic ordering is used instead. Hard-constraint precedence is enforced after the API response.
