# Final submission checklist

## Before judges open the app

- [ ] Replace `sample/messy_catalog.csv` with the official challenge data (or upload it from the UI).
- [ ] Run `python backend/scripts/validate_catalog.py <official_catalog>` to confirm the quality score.
- [ ] Map every official required field to the canonical model in `ALIASES` (`data_pipeline.py:ALIASES`).
- [ ] Set `REQUIRED_FIELDS` in `.env` to match the organizer schema exactly.
- [ ] Run `make check` — all automated tests must pass.

## Functional verification

- [ ] Run a **vague query** — confirm probing layer fires and questions are relevant.
- [ ] Run a **fully specified query** — confirm probing is skipped and top 3 are shown.
- [ ] Run a **negative-constraint query** (e.g. "without Slack") — confirm excluded products do not appear at the top.
- [ ] Confirm hard-constraint violations are visually flagged (amber card border) when the strict pool is too small.
- [ ] Expand the evidence `details` — verify every "Why it fits" bullet maps to a catalogue field.

## Devpost submission

- [ ] Add GitHub repository link in "Try it out".
- [ ] Add live-demo URL (if deploying).
- [ ] Upload 2–3 screenshots: data quality sidebar, probing questions, top-3 with evidence expanded.
- [ ] Optionally: record a 60–90 second screen recording following `docs/DEMO_SCRIPT.md`.
- [ ] Submit before the deadline (Oct 3, 2026 · 7:30 PM GMT+5:30).
