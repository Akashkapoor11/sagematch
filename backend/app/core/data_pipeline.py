import csv
import io
import json
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

from .models import DataIssue, DataQualityReport, Product

ALIASES = {
    'id': ['id', 'product_id', 'sku', 'productid'],
    'name': ['name', 'product', 'product_name', 'tool', 'software', 'software_name'],
    'category': ['category', 'type', 'product_type', 'segment', 'vertical'],
    'description': ['description', 'summary', 'details', 'about', 'product_description'],
    'team_size_min': ['team_size_min', 'min_users', 'users_min', 'minimum_users', 'min_team_size'],
    'team_size_max': ['team_size_max', 'max_users', 'users_max', 'maximum_users', 'max_team_size'],
    'team_size': ['team_size', 'team_size_range', 'users', 'employees', 'user_count', 'team'],
    'integrations': ['integrations', 'integration', 'connectors', 'apps', 'supported_integrations'],
    'features': ['features', 'feature', 'capabilities', 'key_features', 'functionality'],
    'deployment': ['deployment', 'hosting', 'deployments', 'hosting_options', 'hosting_model'],
    'pricing_tier': ['pricing_tier', 'price', 'pricing', 'plan', 'pricing_band', 'price_band'],
    'website': ['website', 'url', 'link', 'homepage', 'product_url'],
}

LIST_SPLIT = re.compile(r'\s*(?:,|;|\||/|\band\b)\s*', re.I)
TOKEN = re.compile(r'[^a-z0-9]+')

CATEGORY_CANONICAL = {
    'crm': 'CRM', 'customer relationship management': 'CRM', 'customer relationship management system': 'CRM',
    'sales crm': 'CRM', 'project management': 'Project Management', 'pm': 'Project Management',
    'hr': 'HR', 'human resources': 'HR', 'marketing': 'Marketing', 'helpdesk': 'Helpdesk', 'customer support': 'Helpdesk',
    'support': 'Helpdesk', 'finance': 'Finance', 'accounting': 'Finance', 'analytics': 'Analytics',
    'business intelligence': 'Analytics', 'collaboration': 'Collaboration', 'communication': 'Collaboration',
    'devops': 'DevOps', 'developer operations': 'DevOps', 'developer platform': 'DevOps',
    'security': 'Security', 'design': 'Design', 'erp': 'ERP',
}

LIST_CANONICAL = {
    'google workspace': 'Google Workspace', 'google drive': 'Google Drive', 'microsoft teams': 'Microsoft Teams',
    'ms teams': 'Microsoft Teams', 'salesforce': 'Salesforce', 'hubspot': 'HubSpot', 'jira': 'Jira',
    'github': 'GitHub', 'zapier': 'Zapier', 'slack': 'Slack', 'zoom': 'Zoom', 'shopify': 'Shopify',
    'quickbooks': 'QuickBooks', 'saml': 'SAML', 'okta': 'Okta', 'gmail': 'Gmail',
}
DEPLOYMENT_CANONICAL = {
    'cloud': 'Cloud', 'cloud hosted': 'Cloud', 'cloud-hosted': 'Cloud', 'saas': 'SaaS',
    'self hosted': 'Self-hosted', 'self-hosted': 'Self-hosted', 'on premise': 'On-premise',
    'on-premise': 'On-premise', 'on premises': 'On-premise', 'hybrid': 'Hybrid',
}


def slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    return TOKEN.sub('_', s).strip('_')


def normalize_text(value: Any) -> str:
    if value is None:
        return ''
    return re.sub(r'\s+', ' ', str(value).replace('\u00a0', ' ')).strip()


def canonicalize_list_item(item: str) -> str:
    text = normalize_text(item)
    key = slug(text).replace('_', ' ')
    if key in LIST_CANONICAL:
        return LIST_CANONICAL[key]
    if key in DEPLOYMENT_CANONICAL:
        return DEPLOYMENT_CANONICAL[key]
    return text


def parse_list(value: Any) -> List[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else LIST_SPLIT.split(normalize_text(value))
    out: List[str] = []
    seen = set()
    for item in raw:
        clean = canonicalize_list_item(item)
        if not clean:
            continue
        key = slug(clean)
        if key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def parse_int(value: Any):
    if value is None or normalize_text(value) == '':
        return None
    s = normalize_text(value).lower().replace(',', '')
    # Team sizes are integers; decimals and negatives are not silently coerced.
    if re.search(r'(?<!\d)-\d+', s) or re.search(r'\d+\.\d+', s):
        return None
    nums = [int(x) for x in re.findall(r'\d+', s)]
    return nums[0] if nums else None


def normalize_category(value: str) -> str:
    v = normalize_text(value)
    if not v:
        return 'Other'
    return CATEGORY_CANONICAL.get(v.lower(), v.title())


def parse_team_range(value: Any) -> Tuple[int | None, int | None]:
    if value is None:
        return None, None
    s = normalize_text(value).lower().replace(',', '')
    if re.search(r'\d+\.\d+', s) or re.search(r'(?<!\d)-\d+', s):
        return None, None
    if any(x in s for x in ('unlimited', 'any size', 'all sizes')):
        return 1, 100000
    nums = [int(x) for x in re.findall(r'\d+', s)]
    if len(nums) >= 2:
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    if len(nums) == 1:
        if '+' in s or 'more' in s:
            return nums[0], 100000
        if 'up to' in s or 'under' in s or 'less than' in s:
            return 1, nums[0]
        return nums[0], nums[0]
    return None, None


def normalize_team_bounds(minimum, maximum):
    min_v = parse_int(minimum)
    max_v = parse_int(maximum)
    if min_v is None or max_v is None:
        return min_v, max_v, False
    if min_v > max_v:
        return max_v, min_v, True
    return min_v, max_v, False


def normalize_url(url: str) -> str:
    url = normalize_text(url)
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    return url.rstrip('/')


def valid_url(url: str) -> bool:
    if not url:
        return True
    try:
        p = urlparse(url)
        return bool(p.scheme in {'http', 'https'} and p.netloc and '.' in p.netloc)
    except Exception:
        return False


def canonical_columns(headers: Iterable[str]) -> Dict[str, str]:
    norm = {slug(h): h for h in headers if h is not None}
    mapping: Dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if slug(alias) in norm:
                mapping[canonical] = norm[slug(alias)]
                break
    return mapping


def _load_rows(content: bytes, filename: str):
    text = content.decode('utf-8-sig', errors='replace')
    suffix = filename.lower().rsplit('.', 1)[-1] if '.' in filename else 'csv'
    if suffix == 'json':
        raw = json.loads(text)
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            rows = raw.get('products', raw.get('data', []))
        else:
            raise ValueError('JSON must contain an array or an object with products/data.')
        if not isinstance(rows, list):
            raise ValueError('JSON must contain an array or a products/data array.')
        rows = [dict(r) for r in rows if isinstance(r, dict)]
        headers = set()
        for row in rows:
            headers.update(row.keys())
        return rows, list(headers)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [dict(r) for r in reader], reader.fieldnames or []


def ingest_bytes(content: bytes, filename: str, guideline_fields: List[str] | None = None):
    rows, headers = _load_rows(content, filename)
    mapping = canonical_columns(headers)
    report = DataQualityReport(rows_received=len(rows))
    products: List[Product] = []
    seen = {}
    used_ids = set()
    accepted_rows = set()
    repair = Counter()
    missing = Counter()

    required = list(guideline_fields or ['name', 'category', 'description'])
    missing_required_fields = [field for field in required if field not in mapping]
    if missing_required_fields:
        for field in missing_required_fields:
            report.issues.append(DataIssue(row=1, field=field, issue='Required canonical field not found in source headers', severity='error'))
        raise ValueError('Missing required canonical fields: ' + ', '.join(missing_required_fields))

    for idx, row in enumerate(rows, start=2):
        def get(c):
            return row.get(mapping[c], '') if c in mapping else ''

        name = normalize_text(get('name'))
        category = normalize_category(get('category'))
        desc = normalize_text(get('description'))

        if name == '':
            report.rows_rejected += 1
            report.issues.append(DataIssue(row=idx, field='name', issue='Missing product name', severity='error'))
            continue
        if not desc:
            missing['description'] += 1
        if not get('category'):
            missing['category'] += 1

        team_min, team_max = parse_team_range(get('team_size')) if 'team_size' in mapping else (None, None)
        explicit_min, explicit_max, swapped = normalize_team_bounds(get('team_size_min'), get('team_size_max'))
        if explicit_min is not None or explicit_max is not None:
            team_min, team_max = explicit_min, explicit_max
        elif team_min is not None or team_max is not None:
            repair['team_size_range'] += 1
        if swapped:
            repair['team_size_bounds'] += 1
            report.issues.append(DataIssue(row=idx, field='team_size', issue='Minimum/maximum bounds were reversed and repaired', severity='warning'))

        raw_integrations = get('integrations')
        raw_features = get('features')
        raw_deployment = get('deployment')
        integrations = parse_list(raw_integrations)
        features = parse_list(raw_features)
        raw_deployment_text = normalize_text(raw_deployment)
        invalid_deployment_urls = re.findall(r'(?:https?://|www\.)\S+', raw_deployment_text, re.I)
        if invalid_deployment_urls:
            raw_deployment_text = re.sub(r'(?:https?://|www\.)\S+', ' ', raw_deployment_text, flags=re.I)
            report.issues.append(DataIssue(row=idx, field='deployment', issue='URL-like deployment value removed as invalid source data', severity='warning'))
            repair['invalid_deployment'] += len(invalid_deployment_urls)
        deployment = parse_list(raw_deployment_text)
        pricing = normalize_text(get('pricing_tier'))
        website = normalize_url(get('website'))

        if website and not valid_url(website):
            repair['invalid_url'] += 1
            report.issues.append(DataIssue(row=idx, field='website', issue='Malformed URL; kept normalized value but flagged it', severity='warning', original=website))
        elif get('website') and normalize_text(get('website')) != website:
            repair['url_normalization'] += 1

        if normalize_text(get('category')) != category:
            repair['category'] += 1
        if normalize_text(get('name')) != name:
            repair['name'] += 1
        if normalize_text(get('description')) != desc:
            repair['description'] += 1
        if normalize_text(raw_integrations) != ', '.join(integrations):
            repair['integration_normalization'] += 1
        if normalize_text(raw_features) != ', '.join(features):
            repair['feature_normalization'] += 1
        if normalize_text(raw_deployment) != ', '.join(deployment):
            repair['deployment_normalization'] += 1

        # Preserve source columns that are not part of our canonical model.
        canonical_source = {source_key for source_key in mapping.values()}
        extra_fields = {
            str(k): v for k, v in row.items()
            if k not in canonical_source and normalize_text(v) != ''
        }

        # Name + website catches obvious duplicates while retaining products with distinct URLs.
        name_key = slug(name).replace('_', '')
        url_key = slug(website.replace('https://', '').replace('http://', '')) if website else ''
        dedupe_key = f'{name_key}|{url_key}' if url_key else name_key
        if dedupe_key in seen:
            report.duplicates_removed += 1
            report.issues.append(DataIssue(row=idx, field='name', issue='Duplicate product removed', severity='warning', original=name))
            continue
        seen[dedupe_key] = idx

        source_pid = normalize_text(get('id'))
        pid = source_pid or f'prod-{len(products) + 1:04d}'
        if pid in used_ids:
            report.issues.append(DataIssue(row=idx, field='id', issue='Duplicate product ID detected; assigned a unique generated ID', severity='warning', original=pid))
            repair['duplicate_id'] += 1
            base_pid = pid
            suffix = 2
            while pid in used_ids:
                pid = f'{base_pid}-{suffix}'
                suffix += 1
        used_ids.add(pid)
        products.append(Product(
            id=pid,
            name=name,
            category=category,
            description=desc,
            team_size_min=team_min,
            team_size_max=team_max,
            integrations=integrations,
            features=features,
            deployment=deployment,
            pricing_tier=pricing,
            website=website,
            source_row=idx,
            extra_fields=extra_fields,
        ))
        report.rows_accepted += 1
        accepted_rows.add(idx)

    report.repair_counts = dict(repair)
    report.missing_counts = dict(missing)
    accepted_errors = sum(1 for issue in report.issues if issue.severity == 'error' and issue.row in accepted_rows)
    accepted_malformed_warnings = sum(1 for issue in report.issues if issue.severity == 'warning' and issue.row in accepted_rows and issue.field == 'website')
    accepted_invalid_deployment_warnings = sum(1 for issue in report.issues if issue.severity == 'warning' and issue.row in accepted_rows and issue.field == 'deployment')
    accepted = max(1, report.rows_accepted)
    # This is a post-sanitization health score. Correctly rejected rows and removed
    # duplicates are reported as separate audit outcomes rather than treated as defects
    # in the clean dataset. The score focuses on residual quality problems among data kept.
    accepted_missing_description_rate = missing.get('description', 0) / accepted
    error_penalty = min(35.0, accepted_errors * 2.0)
    warning_penalty = min(6.0, accepted_malformed_warnings * 0.75 + accepted_invalid_deployment_warnings * 0.5)
    score = 100.0 - accepted_missing_description_rate * 6.0 - error_penalty - warning_penalty
    report.score = round(max(0.0, min(100.0, score)), 1)
    return products, report
