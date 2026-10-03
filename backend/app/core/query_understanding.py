import re
from collections import Counter
from math import log
from typing import Dict, List, Tuple

from .models import CustomerNeeds, Product

CATEGORY_ALIASES = {
    'customer relationship management': 'CRM', 'sales crm': 'CRM', 'crm': 'CRM',
    'project management': 'Project Management', 'project management software': 'Project Management', 'pm': 'Project Management',
    'human resources': 'HR', 'hr': 'HR', 'marketing': 'Marketing', 'customer support': 'Helpdesk', 'helpdesk': 'Helpdesk', 'support': 'Helpdesk',
    'accounting': 'Finance', 'finance': 'Finance', 'business intelligence': 'Analytics', 'analytics': 'Analytics',
    'collaboration': 'Collaboration', 'communication': 'Collaboration', 'devops': 'DevOps', 'developer operations': 'DevOps',
    'security': 'Security', 'design': 'Design', 'erp': 'ERP'
}

INTEGRATION_ALIASES = {
    'slack': 'Slack', 'microsoft teams': 'Microsoft Teams', 'ms teams': 'Microsoft Teams', 'google drive': 'Google Drive',
    'google workspace': 'Google Workspace', 'salesforce': 'Salesforce', 'hubspot': 'HubSpot', 'jira': 'Jira', 'github': 'GitHub',
    'zapier': 'Zapier', 'zoom': 'Zoom', 'shopify': 'Shopify', 'quickbooks': 'QuickBooks', 'saml': 'SAML', 'okta': 'Okta', 'gmail': 'Gmail'
}

DEPLOYMENT_ALIASES = {
    'self-hosted': 'Self-hosted', 'self hosted': 'Self-hosted', 'on-premise': 'On-premise', 'on premise': 'On-premise',
    'on premises': 'On-premise', 'cloud': 'Cloud', 'saas': 'SaaS', 'hybrid': 'Hybrid'
}

PRICING = {
    'free': 'Free', 'freemium': 'Freemium', 'cheap': '$', 'budget': '$', 'affordable': '$',
    'mid-range': '$$', 'mid range': '$$', 'premium': '$$$', 'enterprise': '$$$$',
}

FEATURE_ALIASES = {
    'lead management': ['lead management', 'lead routing'],
    'pipeline': ['pipeline'],
    'automation': ['automation', 'automations', 'workflow automation'],
    'analytics': ['analytics', 'analysis'],
    'reporting': ['reporting', 'reports'],
    'kanban': ['kanban'],
    'gantt': ['gantt'],
    'workflow': ['workflow', 'workflows'],
    'time tracking': ['time tracking', 'timesheets'],
    'invoicing': ['invoicing', 'invoices'],
    'ai': ['ai', 'artificial intelligence'],
    'api': ['api', 'apis'],
    'mobile': ['mobile', 'ios', 'android'],
    'permissions': ['permissions', 'role based access'],
    'approvals': ['approvals', 'approval workflows'],
    'chat': ['chat', 'messaging'],
    'tickets': ['tickets', 'ticketing'],
    'knowledge base': ['knowledge base'],
    'forecasting': ['forecasting', 'forecasts'],
    'dashboards': ['dashboards', 'dashboard'],
    'collaboration': ['collaboration'],
}


def _contains(low: str, phrase: str) -> bool:
    return re.search(rf'(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])', low) is not None


def _extract_team_size(low: str):
    patterns = [
        r'(?:team|sales team|engineering team|users|people|employees|members)\s*(?:of|is|=|around|about)?\s*(\d+)\b',
        r'\b(\d+)\s*(?:-\s*)?(?:person|people|users|employees|members)\b',
        r'\b(?:for|with)\s+(\d+)\s*(?:user|users|person|people|employees|members)\b',
    ]
    for pattern in patterns:
        m = re.search(pattern, low)
        if m:
            return int(m.group(1))
    return None


def _normalise_answer_list(value) -> List[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else re.split(r'[,;|/]+', str(value))
    return [str(v).strip() for v in values if str(v).strip()]


def parse(query: str, answers: Dict | None = None) -> CustomerNeeds:
    q = query.strip()
    low = q.lower()
    answers = answers or {}

    category = next((canonical for phrase, canonical in sorted(CATEGORY_ALIASES.items(), key=lambda x: -len(x[0])) if _contains(low, phrase)), None)
    team_size = _extract_team_size(low)

    integrations = [canonical for phrase, canonical in sorted(INTEGRATION_ALIASES.items(), key=lambda x: -len(x[0])) if _contains(low, phrase)]
    deployment = [canonical for phrase, canonical in sorted(DEPLOYMENT_ALIASES.items(), key=lambda x: -len(x[0])) if _contains(low, phrase)]
    pricing = next((canonical for phrase, canonical in PRICING.items() if _contains(low, phrase)), None)

    features: List[str] = []
    for canonical, phrases in FEATURE_ALIASES.items():
        if any(_contains(low, phrase) for phrase in phrases):
            features.append(canonical)

    excluded_integrations = []
    for phrase, canonical in INTEGRATION_ALIASES.items():
        if re.search(rf'\b(?:without|no|not)\s+(?:[a-z ]*?)?{re.escape(phrase)}\b', low):
            excluded_integrations.append(canonical)
            if canonical in integrations:
                integrations.remove(canonical)

    # Answers override or enrich extracted requirements.
    if answers.get('category'):
        category = str(answers['category']).strip()
    if answers.get('team_size'):
        values = re.findall(r'\d+', str(answers['team_size']))
        if values:
            team_size = int(values[0])
    for field, target in [('integrations', integrations), ('features', features), ('deployment', deployment)]:
        for value in _normalise_answer_list(answers.get(field)):
            target.append(value)
    if answers.get('pricing_tier'):
        pricing = str(answers['pricing_tier']).strip()
    # budget_text is an optional free-text budget note supplied via the probe answer;
    # default to None when the answer was not provided.
    budget_text = str(answers['budget_text']).strip() if answers.get('budget_text') else None

    integrations = list(dict.fromkeys(integrations))
    features = list(dict.fromkeys(features))
    deployment = list(dict.fromkeys(deployment))
    excluded_integrations = list(dict.fromkeys(excluded_integrations))

    must_haves: List[str] = []
    if category:
        must_haves.append(f'Category: {category}')
    if team_size is not None:
        must_haves.append(f'Team size: {team_size}')
    must_haves += [f'Integration: {x}' for x in integrations]
    must_haves += [f'Deployment: {x}' for x in deployment]
    must_haves += [f'Feature: {x}' for x in features]
    if pricing:
        must_haves.append(f'Pricing: {pricing}')

    explicit_dimensions = sum(bool(x) for x in [category, team_size is not None, integrations, features, deployment, pricing])
    confidence = min(0.95, 0.15 + explicit_dimensions * 0.12 + min(0.18, len(q.split()) / 120))
    notes = []
    if excluded_integrations:
        notes.append('Negative integration constraints were detected and will be enforced as exclusions.')
    if not category:
        notes.append('Category is unresolved from the query.')
    if not integrations:
        notes.append('No integration requirement is explicit.')
    if team_size is None:
        notes.append('Team size is unresolved from the query.')

    return CustomerNeeds(
        raw_query=q,
        category=category,
        team_size=team_size,
        integrations=integrations,
        features=features,
        deployment=deployment,
        pricing_tier=pricing,
        budget_text=budget_text,
        must_haves=must_haves,
        excluded_integrations=excluded_integrations,
        confidence=round(confidence, 2),
        extraction_notes=notes,
    )


def _field_values(products: List[Product], field: str):
    values = []
    for p in products:
        if field == 'team_size':
            if p.team_size_min is None and p.team_size_max is None:
                continue
            raw = (p.team_size_min, p.team_size_max)
        else:
            raw = getattr(p, field)
        if isinstance(raw, list):
            values.append(tuple(sorted({str(v).lower() for v in raw})))
        elif raw not in (None, ''):
            values.append(str(raw).lower())
    return values


def _entropy(values: List):
    if not values:
        return 0.0
    counts = Counter(values)
    n = len(values)
    return -sum((c / n) * log(c / n, 2) for c in counts.values())


def _candidate_pool(products: List[Product], needs: CustomerNeeds):
    pool = products
    if needs.category:
        exact = [p for p in products if p.category.lower() == needs.category.lower()]
        if exact:
            pool = exact
    return pool


def _impact_for_dimension(products: List[Product], field: str, needs: CustomerNeeds) -> Tuple[float, List[str]]:
    pool = _candidate_pool(products, needs)
    values = _field_values(pool, field)
    if len(pool) < 2 or len(set(values)) < 2:
        return 0.0, []
    base = _entropy(values)
    options = []
    if field in {'integrations', 'features', 'deployment'}:
        options = sorted({item for p in pool for item in getattr(p, field) if item})[:8]
    elif field == 'pricing_tier':
        options = sorted({p.pricing_tier for p in pool if p.pricing_tier})[:8]
    elif field == 'team_size':
        options = []
    return min(1.0, base / max(1.0, log(max(2, len(pool)), 2))), options


def probe(products: List[Product], needs: CustomerNeeds, max_questions: int = 3):
    """Choose the missing dimensions that provide the most decision value in this catalogue.

    We only probe when the request is genuinely under-specified: category-only requests
    or requests with at most one meaningful constraint. A sufficiently specified request
    should proceed directly to ranking instead of annoying the user with needless questions.
    """
    constraints = sum(bool(x) for x in [needs.category, needs.team_size is not None, needs.integrations, needs.features, needs.deployment, needs.pricing_tier])
    if needs.category and constraints >= 3:
        return []

    candidates = []
    if not needs.category:
        cats = sorted({p.category for p in products if p.category})
        if len(cats) > 1:
            # Category is the first branching question: it changes the search universe, so asking
            # downstream questions before it would be less meaningful.
            return [('category', 'What type of software do you need?', 'Category changes the candidate set most directly.', cats[:8], 1.0)]

    if needs.team_size is None:
        impact, _ = _impact_for_dimension(products, 'team_size', needs)
        if impact > 0:
            candidates.append(('team_size', 'How many people will use the software?', 'Team-size limits can eliminate otherwise similar products.', [], min(1.0, 0.55 + impact * 0.45)))

    if not needs.integrations:
        impact, options = _impact_for_dimension(products, 'integrations', needs)
        if impact > 0.05:
            candidates.append(('integrations', 'Which integrations are must-haves?', 'Required integrations often act as a hard fit constraint.', options, impact))

    if not needs.deployment:
        impact, options = _impact_for_dimension(products, 'deployment', needs)
        if impact > 0.05:
            candidates.append(('deployment', 'Which deployment model do you require: cloud/SaaS, self-hosted, on-premise, or hybrid?', 'Deployment restrictions can rule out otherwise strong products.', options, impact))

    if not needs.pricing_tier:
        impact, options = _impact_for_dimension(products, 'pricing_tier', needs)
        if impact > 0.05:
            candidates.append(('pricing_tier', 'What pricing level fits your budget?', 'Budget constraints can materially reorder otherwise similar options.', options, impact))

    # A feature question is useful only when feature coverage materially varies.
    if not needs.features:
        pool = _candidate_pool(products, needs)
        unique_features = len({f.lower() for p in pool for f in p.features})
        if unique_features > 3:
            candidates.append(('features', 'Which capabilities are must-haves?', 'Feature requirements separate products with otherwise similar profiles.', sorted({f for p in pool for f in p.features})[:8], min(0.85, unique_features / 12)))

    candidates.sort(key=lambda item: (-item[4], item[0]))
    return candidates[:max_questions]
