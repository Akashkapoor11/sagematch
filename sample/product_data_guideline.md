# Demo Product Data Guideline

This file is a **demo stand-in** so the application can be tested before the organizers provide their official kickoff guideline. Replace this with the official guideline during the hackathon and map the supplied schema in `backend/app/core/data_pipeline.py`.

Required canonical fields for the demo: `name`, `category`, `description`.

Optional canonical fields: `id`, `team_size_min`, `team_size_max`, `integrations`, `features`, `deployment`, `pricing_tier`, `website`.

Normalization expectations: trim whitespace, normalize category naming, convert team ranges to numeric bounds, split list fields consistently, deduplicate case/spacing variants, preserve unknown data rather than inventing facts, and report rejected rows/repairs.
