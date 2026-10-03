# 90-second judge demo script

---

## 0–15s — The problem (data quality)

Open the dashboard. Point to the data-quality sidebar:

> *"SageMatch does not trust messy catalogue data — it cleans it first. This demo
> catalogue contains 39 rows with mixed delimiters, inconsistent categories, team-range
> variants, duplicate listings, URL-like deployment noise, and two rows with no product name
> that are rejected entirely. After sanitization, 34 products remain and the health score
> measures the quality of the retained dataset; the audit panel still exposes every repair
> and rejection."*

Open the browser DevTools Network tab briefly to show the `/api/catalog/stats` call returning the real quality report.

---

## 15–35s — Probing

Click the **Ambiguous request** chip: *"I need software for my business."*

> *"Instead of guessing, the system identifies the highest-impact missing dimension.
> With no category known, the entire search space is open — so it asks exactly one
> targeted question with real catalogue options. Notice the expected decision impact
> percentage: this tells the user why the question matters."*

---

## 35–60s — Grounded recommendation

Click **CRM + Slack**: *"I need a CRM for a 20-person sales team that integrates with Slack."*

Point to the three cards:

> *"Five catalogue products satisfy all three hard constraints — CRM category, team size
> 20 within range, and Slack integration present. Only those five are eligible for the top
> three. The score bar shows the composite fit across seven weighted dimensions."*

---

## 60–75s — Explainability

Expand the `details` section on the top card.

> *"Every claim is grounded in the sanitized catalogue. The green rows are confirmed matches
> from the actual CSV field values. The amber rows are gaps — things the customer didn't
> specify, shown transparently instead of being hidden. The score breakdown shows exactly
> how much each dimension contributed."*

---

## 75–90s — Negative constraint

Click **CRM without Slack**: *"We need a CRM that does not use Slack — our team uses Microsoft Teams only."*

> *"Negative constraints work too. The engine removes Slack-integrated products from the
> strict pool. Any result that still includes Slack is penalized by 0.08× and marked as a relaxed fallback only when strict results are insufficient. The 'why it fits' bullets stay grounded in the retained catalogue evidence."*

---

## Optional 20-second engineering walkthrough

- Show `make check` (backend tests + React build + validate + evaluate) running in terminal.
- Open `docs/REASONING.md` for the full decision trace.
- Mention: FastAPI, PostgreSQL, Pydantic v2, API-first LLM adapter, the full automated regression suite, Docker Compose.
