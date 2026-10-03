import math
import re
from collections import Counter
from typing import Dict, List, Tuple

from .models import CustomerNeeds, EvidenceItem, Product, Recommendation

TOKEN_RE = re.compile(r'[a-z0-9]+')
STOP = {'the', 'a', 'an', 'for', 'with', 'and', 'or', 'to', 'of', 'in', 'on', 'my', 'need', 'software', 'tool', 'please', 'i', 'we', 'our', 'is', 'are', 'that', 'this'}
SYNONYMS = {
    'dashboard': 'dashboards', 'dashboards': 'dashboards', 'report': 'reporting', 'reports': 'reporting',
    'automation': 'automation', 'automations': 'automation', 'workflow': 'workflow', 'workflows': 'workflow',
    'crm': 'crm', 'customer': 'customer', 'relationship': 'relationship', 'management': 'management',
    'selfhosted': 'self-hosted', 'self': 'self', 'hosted': 'hosted', 'onpremise': 'on-premise',
}

# Weighting intentionally gives explicit product requirements more influence than generic semantic similarity.
WEIGHTS = {
    'category': 0.27,
    'team_size': 0.15,
    'integrations': 0.21,
    'deployment': 0.12,
    'features': 0.16,
    'pricing': 0.05,
    'semantic': 0.04,
}


def tokens(text):
    out = []
    for t in TOKEN_RE.findall((text or '').lower()):
        if t in STOP:
            continue
        out.append(SYNONYMS.get(t, t))
    return out


def _tfidf_vector(text: str, idf: Dict[str, float]) -> Dict[str, float]:
    counts = Counter(tokens(text))
    total = max(1, sum(counts.values()))
    return {term: (count / total) * idf.get(term, 1.0) for term, count in counts.items()}


def corpus_idf(products: List[Product]) -> Dict[str, float]:
    docs = []
    for p in products:
        docs.append(set(tokens(' '.join([p.name, p.category, p.description, *p.features, *p.integrations, *p.deployment]))))
    df = Counter(term for doc in docs for term in doc)
    n = max(1, len(docs))
    return {term: math.log((1 + n) / (1 + freq)) + 1.0 for term, freq in df.items()}


def semantic_similarity(query: str, document: str, idf: Dict[str, float]) -> float:
    qv = _tfidf_vector(query, idf)
    dv = _tfidf_vector(document, idf)
    if not qv or not dv:
        return 0.0
    dot = sum(qv.get(k, 0.0) * dv.get(k, 0.0) for k in qv.keys() & dv.keys())
    qn = math.sqrt(sum(v * v for v in qv.values()))
    dn = math.sqrt(sum(v * v for v in dv.values()))
    return dot / (qn * dn) if qn and dn else 0.0


def list_match(required: List[str], actual: List[str]) -> Tuple[float, List[str], List[str]]:
    if not required:
        return 0.5, [], []
    actual_map = {str(v).lower(): str(v) for v in actual}
    matched = [req for req in required if req.lower() in actual_map]
    missing = [req for req in required if req.lower() not in actual_map]
    return len(matched) / len(required), matched, missing


def team_match(team_size, p: Product):
    if team_size is None:
        return 0.5, 'No team-size requirement was supplied.', False
    if p.team_size_min is None and p.team_size_max is None:
        return 0.45, 'Catalog does not specify a supported team-size range.', False
    low = p.team_size_min if p.team_size_min is not None else 1
    high = p.team_size_max if p.team_size_max is not None else 100000
    if low <= team_size <= high:
        return 1.0, f'Supports a team of {team_size} users (catalog range {low}+ to {high if high < 100000 else "unbounded"}).', True
    return 0.0, f'Catalog range {low}+ to {high if high < 100000 else "unbounded"} does not cover {team_size} users.', False


def _deployment_match(required, actual):
    if not required:
        return 0.5, [], []
    return list_match(required, actual)


def score_product(p: Product, n: CustomerNeeds, idf: Dict[str, float] | None = None):
    evidence: List[EvidenceItem] = []
    hard_failures: List[str] = []
    component_scores: Dict[str, float] = {}

    # Category
    if n.category:
        category_ok = p.category.lower() == n.category.lower()
        score = 1.0 if category_ok else 0.0
        component_scores['category'] = score
        evidence.append(EvidenceItem(field='category', status='matched' if category_ok else 'missing', requirement=n.category,
                                     evidence=f'Catalog category: {p.category}.', contribution=score * WEIGHTS['category'], source_row=p.source_row))
        if not category_ok:
            hard_failures.append('category')
    else:
        component_scores['category'] = 0.5

    # Team size
    team_score, team_evidence, team_ok = team_match(n.team_size, p)
    component_scores['team_size'] = team_score
    if n.team_size is not None:
        evidence.append(EvidenceItem(field='team_size', status='matched' if team_ok else ('unknown' if team_score else 'missing'),
                                     requirement=str(n.team_size), evidence=team_evidence, contribution=team_score * WEIGHTS['team_size'], source_row=p.source_row))
        if not team_ok:
            hard_failures.append('team_size')

    # Integrations: explicit requirements are hard constraints when enough compliant candidates exist.
    int_score, int_matched, int_missing = list_match(n.integrations, p.integrations)
    component_scores['integrations'] = int_score if n.integrations else 0.5
    if n.integrations:
        for req in n.integrations:
            ok = req.lower() in {i.lower() for i in p.integrations}
            evidence.append(EvidenceItem(field='integrations', status='matched' if ok else 'missing', requirement=req,
                                         evidence=('Supported by catalog: ' + ', '.join(p.integrations)) if ok else 'No explicit catalog evidence.',
                                         contribution=(1.0 if ok else 0.0) * WEIGHTS['integrations'] / len(n.integrations), source_row=p.source_row))
        if int_missing:
            hard_failures.append('integrations')

    # Exclusions: a product with a forbidden integration receives a strong penalty but remains visible when the candidate set is too small.
    excluded_hits = [x for x in n.excluded_integrations if x.lower() in {i.lower() for i in p.integrations}]
    if excluded_hits:
        hard_failures.append('excluded_integration')

    # Deployment
    dep_score, dep_matched, dep_missing = _deployment_match(n.deployment, p.deployment)
    component_scores['deployment'] = dep_score
    if n.deployment:
        for req in n.deployment:
            ok = req.lower() in {d.lower() for d in p.deployment}
            evidence.append(EvidenceItem(field='deployment', status='matched' if ok else 'missing', requirement=req,
                                         evidence='Supported deployment: ' + ', '.join(p.deployment),
                                         contribution=(1.0 if ok else 0.0) * WEIGHTS['deployment'] / len(n.deployment), source_row=p.source_row))
        if dep_missing:
            hard_failures.append('deployment')

    # Features
    feat_score, feat_matched, feat_missing = list_match(n.features, p.features)
    if n.features:
        matched_feature_count = 0
        for req in n.features:
            ok = req.lower() in {f.lower() for f in p.features} or re.search(r'(?<![a-z0-9])' + re.escape(req.lower()) + r'(?![a-z0-9])', p.description.lower()) is not None
            if ok:
                matched_feature_count += 1
            evidence.append(EvidenceItem(field='features', status='matched' if ok else 'missing', requirement=req,
                                         evidence='Catalogued capabilities: ' + ', '.join(p.features[:8]) + (f'; description evidence: {p.description[:180]}' if ok and req.lower() not in {f.lower() for f in p.features} else ''),
                                         contribution=(1.0 if ok else 0.0) * WEIGHTS['features'] / len(n.features), source_row=p.source_row))
        component_scores['features'] = matched_feature_count / len(n.features)
    else:
        component_scores['features'] = 0.5

    # Pricing is informative rather than hard because the organizer schema may encode it differently.
    if n.pricing_tier:
        pricing_score = 1.0 if p.pricing_tier.lower() == n.pricing_tier.lower() else 0.0 if not p.pricing_tier else 0.5
        component_scores['pricing'] = pricing_score
        evidence.append(EvidenceItem(field='pricing', status='matched' if pricing_score == 1 else 'partial', requirement=n.pricing_tier,
                                     evidence=f'Catalog price tier: {p.pricing_tier or "unspecified"}.', contribution=pricing_score * WEIGHTS['pricing'], source_row=p.source_row))
    else:
        component_scores['pricing'] = 0.5

    semantic_text = ' '.join([p.name, p.category, p.description, *p.features, *p.integrations, *p.deployment])
    semantic = semantic_similarity(n.raw_query, semantic_text, idf or {})
    component_scores['semantic'] = semantic

    active = ['semantic']
    if n.category: active.append('category')
    if n.team_size is not None: active.append('team_size')
    if n.integrations: active.append('integrations')
    if n.deployment: active.append('deployment')
    if n.features: active.append('features')
    if n.pricing_tier: active.append('pricing')
    weight_total = sum(WEIGHTS[key] for key in active)
    final = sum(component_scores[key] * WEIGHTS[key] for key in active) / max(weight_total, 1e-9)

    if 'excluded_integration' in hard_failures:
        final *= 0.08
    elif hard_failures:
        final *= 0.30

    matched_reqs: List[str] = []
    unmet: List[str] = []
    why: List[str] = []
    for item in evidence:
        if item.status == 'matched':
            matched_reqs.append(item.requirement)
            why.append(item.evidence if item.field not in {'category'} else f'{item.requirement} category match.')
        elif item.status in {'missing', 'partial'}:
            unmet.append(f'{item.field.replace("_", " ").title()}: {item.requirement}')

    # Clean duplicate sentences without losing evidence.
    why = list(dict.fromkeys(why))[:6]
    unmet = list(dict.fromkeys(unmet))[:6]
    return max(0.0, min(1.0, final)), why, unmet, hard_failures, evidence, component_scores


def recommend_with_meta(products: List[Product], n: CustomerNeeds, top_k=3, candidate_pool_size=None):
    scored = []
    idf = corpus_idf(products)
    for p in products:
        score, why, unmet, hard, evidence, components = score_product(p, n, idf)
        scored.append((score, p, why, unmet, hard, evidence, components))

    # Build a compliant candidate pool. We only relax hard constraints when strict compliance leaves fewer than top_k options.
    def is_strict(item):
        return len(item[4]) == 0

    strict_pool = [item for item in scored if is_strict(item)]
    if len(strict_pool) >= top_k:
        scored = strict_pool
        relaxed = False
    else:
        # If the catalogue cannot satisfy all hard requirements three times, keep every
        # fully compliant candidate ahead of relaxed alternatives. Never let a hard-failing
        # product outrank a compliant one merely because its weighted score is higher.
        relaxed_pool = [item for item in scored if not is_strict(item)]
        strict_pool = sorted(strict_pool, key=lambda item: (-item[0], item[1].name.lower()))
        relaxed_pool = sorted(relaxed_pool, key=lambda item: (-item[0], item[1].name.lower()))
        scored = strict_pool + relaxed_pool
        relaxed = True

    if not relaxed:
        scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    out = []
    limit = candidate_pool_size or top_k
    for idx, (score, p, why, unmet, hard, evidence, components) in enumerate(scored[:limit], start=1):
        if not why:
            why = ['No explicit requirement evidence beyond the catalogue text was detected.']
        if not unmet:
            unmet = ['No explicit gaps were detected; verify plan-level limits against the organizer data.']
        match_summary = f'{round(score * 100)}% fit score · ' + ', '.join(
            f'{key.replace("_", " ")} {round(value * 100)}%'
            for key, value in components.items() if key != 'semantic' and value not in {0.5}
        )
        out.append(Recommendation(
            rank=idx,
            product=p,
            score=round(score, 4),
            match_summary=match_summary,
            why_recommended=why,
            improve_fit=unmet,
            matched_requirements=list(dict.fromkeys(e.requirement for e in evidence if e.status == 'matched'))[:8],
            unmet_requirements=list(dict.fromkeys(e.requirement for e in evidence if e.status in {'missing', 'partial'}))[:8],
            evidence=evidence,
            score_breakdown={k: round(v, 4) for k, v in components.items()},
            hard_constraints_satisfied=(len(hard) == 0),
        ))
    return out, {'strict_pool_size': len(strict_pool), 'relaxed_constraints': relaxed}


def recommend(products: List[Product], n: CustomerNeeds, top_k=3):
    results, _ = recommend_with_meta(products, n, top_k)
    return results
