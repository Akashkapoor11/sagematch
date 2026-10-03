from pathlib import Path
from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .core.config import APP_NAME, CORS_ALLOWED_ORIGINS, LLM_MODEL, MAX_PROBES, REQUIRED_FIELDS
from .core.db import get_quality_report, init_db, list_products, replace_products
from .core.data_pipeline import ingest_bytes
from .core.llm import llm
from .core.models import CustomerNeeds, ProbeQuestion, QueryRequest, QueryResponse
from .core.query_understanding import parse, probe
from .core.ranker import recommend_with_meta

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not list_products():
        _reset_demo()
    yield


app = FastAPI(title=APP_NAME, version='3.0.1', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)
static_dir = Path(__file__).parent / 'static'
frontend_dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if (frontend_dist / 'index.html').exists():
    static_dir = frontend_dist
if static_dir.exists():
    app.mount('/static', StaticFiles(directory=static_dir), name='static')
    assets_dir = static_dir / 'assets'
    if assets_dir.exists():
        app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')


DEMO_REQUIRED_FIELDS = ['name', 'category', 'description']

def _reset_demo():
    sample = Path(__file__).resolve().parents[2] / 'sample' / 'messy_catalog.csv'
    products, report = ingest_bytes(sample.read_bytes(), sample.name, DEMO_REQUIRED_FIELDS)
    replace_products(products, report.model_dump())
    return products, report


def _allowed_vocab(products):
    return {
        'categories': sorted({p.category for p in products}),
        'integrations': sorted({i for p in products for i in p.integrations}),
        'features': sorted({f for p in products for f in p.features}),
        'deployment': sorted({d for p in products for d in p.deployment}),
        'pricing': sorted({p.pricing_tier for p in products if p.pricing_tier}),
    }


def _normalize_needs_to_catalog(needs, vocab):
    mapping = {
        'category': vocab['categories'],
        'integrations': vocab['integrations'],
        'features': vocab['features'],
        'deployment': vocab['deployment'],
    }
    allowed = {k: {str(x).lower(): x for x in values} for k, values in mapping.items()}
    if needs.category:
        needs.category = allowed['category'].get(needs.category.lower())
    for key in ('integrations', 'features', 'deployment'):
        values = getattr(needs, key)
        setattr(needs, key, list(dict.fromkeys(allowed[key][str(v).lower()] for v in values if str(v).lower() in allowed[key])))
    if needs.team_size is not None and not (1 <= needs.team_size <= 10_000_000):
        needs.team_size = None
        needs.extraction_notes.append('Invalid team size was discarded during validation.')
    if needs.pricing_tier and vocab['pricing']:
        needs.pricing_tier = next((x for x in vocab['pricing'] if x.lower() == needs.pricing_tier.lower()), None)
    needs.must_haves = []
    if needs.category:
        needs.must_haves.append(f'Category: {needs.category}')
    if needs.team_size is not None:
        needs.must_haves.append(f'Team size: {needs.team_size}')
    needs.must_haves += [f'Integration: {x}' for x in needs.integrations]
    needs.must_haves += [f'Deployment: {x}' for x in needs.deployment]
    needs.must_haves += [f'Feature: {x}' for x in needs.features]
    if needs.pricing_tier:
        needs.must_haves.append(f'Pricing: {needs.pricing_tier}')
    return needs


def _merge_llm(needs, payload, vocab):
    if not payload:
        return needs, False
    category = str(payload.get('category') or '').strip()
    allowed_categories = {x.lower(): x for x in vocab['categories']}
    if category.lower() in allowed_categories:
        needs.category = allowed_categories[category.lower()]
    try:
        if payload.get('team_size') is not None:
            needs.team_size = int(payload['team_size'])
    except (TypeError, ValueError):
        pass
    for key in ('integrations', 'features', 'deployment'):
        vals = payload.get(key)
        if not isinstance(vals, list):
            continue
        existing = getattr(needs, key)
        if key == 'integrations': allowed = {x.lower(): x for x in vocab['integrations']}
        elif key == 'features': allowed = {x.lower(): x for x in vocab['features']}
        else: allowed = {x.lower(): x for x in vocab['deployment']}
        for value in vals:
            canonical = allowed.get(str(value).lower())
            if canonical:
                existing.append(canonical)
        setattr(needs, key, list(dict.fromkeys(existing)))
    if payload.get('pricing_tier'):
        needs.pricing_tier = str(payload['pricing_tier'])
    excluded = payload.get('excluded_integrations', [])
    if isinstance(excluded, list):
        allowed_excluded = {x.lower(): x for x in vocab['integrations']}
        needs.excluded_integrations = list(dict.fromkeys(
            allowed_excluded[str(x).lower()] for x in excluded if str(x).lower() in allowed_excluded
        ))
        needs.integrations = [x for x in needs.integrations if x.lower() not in {e.lower() for e in needs.excluded_integrations}]
    try:
        needs.confidence = max(needs.confidence, min(0.95, float(payload.get('confidence') or 0)))
    except (TypeError, ValueError):
        pass
    needs.must_haves = []
    if needs.category:
        needs.must_haves.append(f'Category: {needs.category}')
    if needs.team_size is not None:
        needs.must_haves.append(f'Team size: {needs.team_size}')
    needs.must_haves += [f'Integration: {x}' for x in needs.integrations]
    needs.must_haves += [f'Deployment: {x}' for x in needs.deployment]
    needs.must_haves += [f'Feature: {x}' for x in needs.features]
    if needs.pricing_tier:
        needs.must_haves.append(f'Pricing: {needs.pricing_tier}')
    return needs, True


@app.get('/', response_class=HTMLResponse)
def home():
    index_path = static_dir / 'index.html'
    if not index_path.exists():
        raise HTTPException(503, 'Frontend build is missing. Run `cd frontend && npm install && npm run build`.')
    return index_path.read_text(encoding='utf-8')


@app.api_route('/api/health', methods=['GET', 'HEAD'])
def health():
    quality = get_quality_report() or {}
    return {
        'status': 'ok',
        'products': len(list_products()),
        'llm_enabled': llm.enabled,
        'quality_score': quality.get('score'),
    }


@app.get('/api/catalog/stats')
def stats():
    products = list_products()
    quality = get_quality_report() or {}
    categories = {p.category: 0 for p in products}
    for p in products:
        categories[p.category] = categories.get(p.category, 0) + 1
    return {
        'products': len(products),
        'categories': categories,
        'integrations': len({i for p in products for i in p.integrations}),
        'features': len({f for p in products for f in p.features}),
        'deployment_models': len({d for p in products for d in p.deployment}),
        'quality_score': quality.get('score'),
        'quality_report': quality,
    }


@app.get('/api/catalog/quality')
def quality():
    return get_quality_report() or {}


@app.post('/api/catalog/upload')
async def upload_catalog(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(('.csv', '.json')):
        raise HTTPException(400, 'Upload a CSV or JSON catalogue.')
    content = await file.read()
    if len(content) > 8_000_000:
        raise HTTPException(413, 'Catalogue file is larger than the 8 MB safety limit.')
    try:
        products, report = ingest_bytes(content, file.filename, REQUIRED_FIELDS)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, f'Could not parse catalogue: {exc}')
    if not products:
        raise HTTPException(400, 'No valid products could be ingested.')
    replace_products(products, report.model_dump())
    return {'report': report.model_dump(), 'products': len(products)}


@app.post('/api/catalog/reset-demo')
def reset_demo():
    products, report = _reset_demo()
    return {'report': report.model_dump(), 'products': len(products)}


@app.post('/api/query', response_model=QueryResponse)
async def query(req: QueryRequest):
    products = list_products()
    if not products:
        raise HTTPException(400, 'No catalogue loaded.')

    # API-FIRST POLICY: every LLM-assisted stage calls the configured API before
    # invoking its deterministic fallback. The local parser is not executed first.
    needs = None
    api_trace = {
        'requirements': {'mode': 'fallback', 'error': 'not attempted'},
        'probing': {'mode': 'fallback', 'error': 'not attempted'},
        'reranking': {'mode': 'fallback', 'error': 'not attempted'},
        'explanations': {'mode': 'fallback', 'error': 'not attempted'},
    }
    vocab = _allowed_vocab(products)

    # 1) Requirements: API first, then local parser fallback.
    extraction = await llm.understand(
        req.query,
        req.answers,
        vocab['categories'],
        vocab['integrations'],
        vocab['features'],
        vocab['deployment'],
        vocab['pricing'],
    )
    if extraction.used_api and extraction.data:
        # API output is the primary source. It is sanitized against the catalog vocabulary.
        needs = CustomerNeeds(raw_query=req.query)
        needs, _ = _merge_llm(needs, extraction.data, vocab)
        needs = _normalize_needs_to_catalog(needs, vocab)
        api_trace['requirements'] = {'mode': 'api', 'model': LLM_MODEL or 'configured-endpoint'}
    else:
        # Only after an API failure/invalid response do we invoke the local parser fallback.
        needs = parse(req.query, req.answers)
        needs = _normalize_needs_to_catalog(needs, vocab)
        api_trace['requirements'] = {'mode': 'fallback', 'error': extraction.error or 'API unavailable'}

    # 2) Probing: when clarification is actually needed, call the API first. The
    # deterministic information-gain planner is the fallback only when the API fails.
    constraints = sum(bool(x) for x in [needs.category, needs.team_size is not None, needs.integrations, needs.features, needs.deployment, needs.pricing_tier])
    needs_probe = not (needs.category and constraints >= 3)
    all_dimensions = ['category', 'team_size', 'integrations', 'features', 'deployment', 'pricing_tier']
    missing_dimensions = [
        field for field in all_dimensions
        if (field == 'category' and not needs.category)
        or (field == 'team_size' and needs.team_size is None)
        or (field == 'integrations' and not needs.integrations)
        or (field == 'features' and not needs.features)
        or (field == 'deployment' and not needs.deployment)
        or (field == 'pricing_tier' and not needs.pricing_tier)
    ]
    raw_probes = []
    if needs_probe and missing_dimensions:
        api_probe = await llm.generate_probes(
            req.query,
            needs.model_dump(),
            missing_dimensions,
            vocab,
            MAX_PROBES,
        )
        if api_probe.used_api and api_probe.data:
            raw_probes = [
                (
                    row['field'], row['question'], row['why_it_matters'],
                    row.get('options', []), row.get('expected_impact', 0.0)
                ) for row in api_probe.data['probes']
            ]
            api_trace['probing'] = {'mode': 'api'}
        else:
            raw_probes = probe(products, needs, MAX_PROBES)
            api_trace['probing'] = {'mode': 'fallback', 'error': api_probe.error or 'API unavailable'}
    elif needs_probe:
        raw_probes = probe(products, needs, MAX_PROBES)
        api_trace['probing'] = {'mode': 'fallback', 'error': 'No API-capable probing dimensions were available.'}
    else:
        api_trace['probing'] = {'mode': 'not_needed'}

    questions = [
        ProbeQuestion(
            id=f'probe_{i + 1}',
            field=field,
            question=question,
            why_it_matters=why,
            options=options,
            expected_impact=round(float(impact), 2),
        )
        for i, (field, question, why, options, impact) in enumerate(raw_probes)
    ]

    if questions and len(req.answers) == 0:
        return QueryResponse(
            status='needs_clarification',
            needs=needs,
            probes=questions,
            trace={
                'llm_used': any(v.get('mode') == 'api' for v in api_trace.values()),
                'api_first_policy': True,
                'api_trace': api_trace,
                'api_policy_summary': 'API first → validate → deterministic fallback on failure',
                'catalog_size': len(products),
                'candidate_categories': vocab['categories'],
                'probing_strategy': 'API-first adaptive probing with information-gain fallback',
                'reasoning': 'Questions are selected from dimensions that can materially partition the candidate set.',
            },
        )

    if questions and len(req.answers) > 0 and any(field not in req.answers for field, *_ in raw_probes):
        unresolved = [q for q in questions if q.field not in req.answers]
        if unresolved:
            return QueryResponse(
                status='needs_clarification',
                needs=needs,
                probes=unresolved,
                recommendations=[],
                trace={
                    'api_first_policy': True,
                    'api_trace': api_trace,
                    'api_policy_summary': 'API first → validate → deterministic fallback on failure',
                    'catalog_size': len(products),
                    'probing_strategy': 'API-first adaptive follow-up',
                },
            )

    # 3) Deterministic, grounded scoring creates the safety boundary. API reranking is
    # allowed only to reorder candidates already admitted by hard constraints.
    candidate_pool_size = min(len(products), max(req.top_k * 8, 24))
    recommendations, rank_meta = recommend_with_meta(products, needs, req.top_k, candidate_pool_size=candidate_pool_size)

    # API-FIRST reranking: when a recommendation stage exists, call the API even when
    # the strict pool is small. The deterministic ranker creates the candidate pool; the
    # API may reorder that exact pool only. After the API responds, we independently enforce
    # strict candidates before relaxed candidates, so the model can never weaken a hard constraint.
    candidate_payload = [
        {
            'id': r.product.id,
            'name': r.product.name,
            'category': r.product.category,
            'deterministic_score': r.score,
            'hard_constraints_satisfied': r.hard_constraints_satisfied,
            'matched_requirements': r.matched_requirements,
            'unmet_requirements': r.unmet_requirements,
            'evidence': [e.model_dump() for e in r.evidence],
            'source_row': r.product.source_row,
        }
        for r in recommendations
    ]
    api_rank = await llm.rerank(req.query, needs.model_dump(), candidate_payload, req.top_k) if candidate_payload else None
    if api_rank and api_rank.used_api and api_rank.data:
        by_id = {r.product.id: r for r in recommendations}
        ordered = [by_id[x] for x in api_rank.data['ordered_product_ids']]
        strict_ids = {r.product.id for r in recommendations if r.hard_constraints_satisfied}
        ordered_strict = [r for r in ordered if r.product.id in strict_ids]
        ordered_relaxed = [r for r in ordered if r.product.id not in strict_ids]
        # The API is trusted only as a within-tier ordering signal. Strict candidates always
        # remain ahead of relaxed fallbacks, regardless of what ordering the model returned.
        recommendations = (ordered_strict + ordered_relaxed)[:req.top_k]
        for idx, item in enumerate(recommendations, start=1):
            item.rank = idx
        api_trace['reranking'] = {'mode': 'api', 'scope': 'full grounded candidate pool; strict precedence enforced'}
    else:
        api_trace['reranking'] = {'mode': 'fallback', 'error': (api_rank.error if api_rank else 'No candidates available')}

    recommendations = recommendations[:req.top_k]
    for idx, item in enumerate(recommendations, start=1):
        item.rank = idx

    # 4) Explanations: API first, but only from evidence already produced by the grounded
    # ranker. Any failed or unsafe response falls back to deterministic explanations.
    explanation_payload = [
        {
            'product_id': r.product.id,
            'product_name': r.product.name,
            'matched_requirements': r.matched_requirements,
            'unmet_requirements': r.unmet_requirements,
            'evidence': [e.model_dump() for e in r.evidence],
        }
        for r in recommendations
    ]
    api_explain = await llm.explain(req.query, needs.model_dump(), explanation_payload)
    if api_explain.used_api and api_explain.data:
        by_id = {x['product_id']: x for x in api_explain.data['recommendations']}
        for r in recommendations:
            item = by_id.get(r.product.id)
            if item:
                r.why_recommended = item['why_recommended']
                r.improve_fit = item['improve_fit']
        api_trace['explanations'] = {'mode': 'api', 'grounding': 'catalog evidence supplied to API'}
    else:
        api_trace['explanations'] = {'mode': 'fallback', 'error': api_explain.error or 'API unavailable'}

    return QueryResponse(
        status='complete',
        needs=needs,
        probes=[],
        recommendations=recommendations,
        trace={
            'llm_used': any(v.get('mode') == 'api' for v in api_trace.values()),
            'api_first_policy': True,
            'api_trace': api_trace,
            'api_policy_summary': 'API first → validate → deterministic fallback on failure',
            'catalog_size': len(products),
            'candidate_categories': vocab['categories'],
            'ranking': 'deterministic constraint-aware ranking with API-first compliant reranking',
            'hard_constraint_policy': 'strict pool when at least top_k compliant candidates exist; otherwise transparent best-effort fallback',
            'explanations_grounded': True,
            **rank_meta,
        },
    )


@app.get('/api/products')
def products():
    return {'products': [p.model_dump() for p in list_products()]}


@app.get('/api/demo-cases')
def demo_cases():
    path = Path(__file__).resolve().parents[2] / 'sample' / 'demo_queries.json'
    return json.loads(path.read_text(encoding='utf-8'))
