"""Repeatable judge-facing evaluation for the bundled demo catalogue.

The official catalogue should replace the demo data at kickoff. This script is deliberately
transparent: it reports hard-constraint violations and probe behavior instead of pretending
that a heuristic score is a benchmark supplied by the organizers.
"""
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.data_pipeline import ingest_bytes
from app.core.query_understanding import parse, probe
from app.core.ranker import recommend_with_meta

ROOT = PROJECT_ROOT
products, quality = ingest_bytes((ROOT / 'sample/messy_catalog.csv').read_bytes(), 'messy_catalog.csv')
cases = json.loads((ROOT / 'sample/demo_queries.json').read_text())

rows = []
for case in cases:
    needs = parse(case['query'], case.get('answers', {}))
    questions = probe(products, needs, 3)
    recs, meta = recommend_with_meta(products, needs, 3)
    hard_violations = sum(not r.hard_constraints_satisfied for r in recs)
    rows.append({
        'label': case.get('label', ''),
        'query': case['query'],
        'parsed': {
            'category': needs.category,
            'team_size': needs.team_size,
            'integrations': needs.integrations,
            'features': needs.features,
            'deployment': needs.deployment,
            'pricing_tier': needs.pricing_tier,
            'excluded_integrations': needs.excluded_integrations,
        },
        'probes': [q[0] for q in questions],
        'top3': [
            {'rank': r.rank, 'name': r.product.name, 'category': r.product.category, 'fit_score': r.score,
             'hard_constraints_satisfied': r.hard_constraints_satisfied}
            for r in recs
        ],
        'hard_constraint_violations': hard_violations,
        'strict_pool_size': meta['strict_pool_size'],
        'relaxed_constraints': meta['relaxed_constraints'],
    })


payload = {
    'catalog': {'rows_received': quality.rows_received, 'rows_accepted': quality.rows_accepted,
                'duplicates_removed': quality.duplicates_removed, 'score': quality.score},
    'queries': rows,
    'summary': {
        'queries_evaluated': len(rows),
        'queries_with_hard_constraint_violations': sum(r['hard_constraint_violations'] > 0 for r in rows),
        'queries_with_probes': sum(bool(r['probes']) for r in rows),
    }
}
print(json.dumps(payload, indent=2, ensure_ascii=False))
