import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT
from .query_understanding import CATEGORY_ALIASES, DEPLOYMENT_ALIASES, FEATURE_ALIASES, INTEGRATION_ALIASES, PRICING, _extract_team_size


@dataclass
class LLMResult:
    data: Optional[Dict[str, Any]]
    used_api: bool
    fallback: bool
    error: Optional[str] = None


class LLMClient:
    """API-first LLM adapter.

    Every LLM-assisted capability attempts the configured API first. Any transport,
    provider, parsing, or schema-validation failure immediately falls back to the
    deterministic implementation supplied by the caller.
    """

    def __init__(self):
        self.enabled = bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)

    async def _chat(self, messages, temperature=0.05) -> LLMResult:
        if not self.enabled:
            return LLMResult(None, used_api=False, fallback=True, error='LLM API is not configured.')

        base = LLM_BASE_URL.rstrip('/')
        if base.endswith('/v1'):
            url = f'{base}/chat/completions'
        else:
            url = f'{base}/v1/chat/completions'
        headers = {
            'Authorization': f'Bearer {LLM_API_KEY}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': LLM_MODEL,
            'messages': messages,
            'temperature': temperature,
            'response_format': {'type': 'json_object'},
        }
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                except httpx.HTTPStatusError as first_exc:
                    # Some OpenAI-compatible/local providers reject response_format even
                    # though they support the same chat-completions route. Retry the API
                    # once without that optional parameter before falling back.
                    if first_exc.response.status_code != 400:
                        raise
                    payload.pop('response_format', None)
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                body = response.json()
                content = body['choices'][0]['message']['content']
                if isinstance(content, list):
                    content = ''.join(str(part.get('text', part)) if isinstance(part, dict) else str(part) for part in content)
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError('LLM returned a non-object JSON response.')
                return LLMResult(parsed, used_api=True, fallback=False)
        except Exception as exc:
            return LLMResult(None, used_api=False, fallback=True, error=f'{type(exc).__name__}: {exc}')

    async def understand(
        self,
        query: str,
        answers: Dict[str, Any],
        allowed_categories: List[str],
        allowed_integrations: List[str],
        allowed_features: List[str],
        allowed_deployment: List[str],
        allowed_pricing: List[str],
    ) -> LLMResult:
        system = '''You are a strict requirements analyst inside a software recommendation engine.
Extract ONLY requirements explicitly supported by the user's text. Never invent requirements and never invent catalogue facts.
Return JSON with: category, team_size, integrations, excluded_integrations, features, deployment, pricing_tier, confidence.
Use only values present in the allowed vocabularies. For 'without/no/not X', put X in excluded_integrations and DO NOT put it in integrations. Keep unknown fields null/empty.'''
        user = {
            'query': query,
            'answers': answers,
            'allowed_categories': allowed_categories,
            'allowed_integrations': allowed_integrations,
            'allowed_features': allowed_features,
            'allowed_deployment': allowed_deployment,
            'allowed_pricing': allowed_pricing,
        }
        result = await self._chat([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(user)},
        ])
        if not result.used_api or not result.data:
            return result
        allowed = {
            'categories': {x.lower() for x in allowed_categories},
            'integrations': {x.lower() for x in allowed_integrations},
            'features': {x.lower() for x in allowed_features},
            'deployment': {x.lower() for x in allowed_deployment},
            'pricing': {x.lower() for x in allowed_pricing},
        }
        try:
            payload = dict(result.data)
            category = payload.get('category')
            if category and str(category).lower() not in allowed['categories']:
                raise ValueError('LLM returned an unknown category outside the catalogue vocabulary.')
            for key in ('integrations', 'excluded_integrations', 'features', 'deployment'):
                values = payload.get(key, [])
                if isinstance(values, str):
                    # Coerce a bare string to a single-element list — common model quirk.
                    values = [values] if values.strip() else []
                    payload[key] = values
                elif not isinstance(values, list):
                    payload[key] = []
                    values = []
                vocabulary = allowed['integrations'] if key in {'integrations', 'excluded_integrations'} else allowed[key]
                unknown = [v for v in values if str(v).lower() not in vocabulary]
                if unknown:
                    raise ValueError(f'LLM returned unknown {key}: {unknown!r}')
                payload[key] = list(dict.fromkeys(values))
            if payload.get('pricing_tier') is not None and str(payload.get('pricing_tier')).lower() not in allowed['pricing']:
                raise ValueError('LLM returned an unknown pricing tier outside the catalogue vocabulary.')
            payload['integrations'] = [v for v in payload.get('integrations', []) if str(v).lower() not in {str(x).lower() for x in payload.get('excluded_integrations', [])}]
            if payload.get('team_size') is not None:
                payload['team_size'] = int(payload['team_size'])
                if not 1 <= payload['team_size'] <= 10_000_000:
                    raise ValueError('team_size must be between 1 and 10000000')
            if payload.get('confidence') is not None:
                payload['confidence'] = max(0.0, min(1.0, float(payload['confidence'])))

            # Contract validation against explicit lexical signals in the user's query.
            # If the API misses an obvious supported requirement, treat that as an API
            # validation failure and invoke the deterministic fallback instead of silently
            # accepting a lossy extraction. This keeps the pipeline API-first without making
            # the model's omissions authoritative.
            query_low = query.lower()
            explicit_category_canonicals = {canonical for phrase, canonical in CATEGORY_ALIASES.items() if re.search(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])', query_low)}
            explicit_categories = [x for x in allowed_categories if x.lower() in {c.lower() for c in explicit_category_canonicals} or re.search(rf'(?<![a-z0-9]){re.escape(x.lower())}(?![a-z0-9])', query_low)]
            if explicit_categories and str(payload.get('category') or '').lower() not in {x.lower() for x in explicit_categories}:
                raise ValueError('LLM omitted an explicit supported category from the query.')
            explicit_integrations = []
            for phrase, canonical in INTEGRATION_ALIASES.items():
                if canonical in allowed_integrations and re.search(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])', query_low):
                    explicit_integrations.append(canonical)
            extracted_integrations = {str(x).lower() for x in payload.get('integrations', [])}
            excluded_integrations = {str(x).lower() for x in payload.get('excluded_integrations', [])}
            explicit_deployments = []
            for phrase, canonical in DEPLOYMENT_ALIASES.items():
                if canonical in allowed_deployment and re.search(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])', query_low):
                    explicit_deployments.append(canonical)
            extracted_deployments = {str(x).lower() for x in payload.get('deployment', [])}
            for deployment in explicit_deployments:
                if deployment.lower() not in extracted_deployments:
                    raise ValueError('LLM omitted an explicit supported deployment model from the query.')

            for integration in explicit_integrations:
                # An explicitly negated integration belongs only in exclusions.
                negated = re.search(rf'\b(?:without|no|not)\s+(?:[a-z ]*?)?{re.escape(integration.lower())}\b', query_low)
                if negated:
                    if integration.lower() not in excluded_integrations:
                        raise ValueError('LLM omitted an explicit excluded integration from the query.')
                elif integration.lower() not in extracted_integrations:
                    raise ValueError('LLM omitted an explicit supported integration from the query.')
            explicit_team_size = _extract_team_size(query_low)
            if explicit_team_size is not None:
                if payload.get('team_size') is None:
                    raise ValueError('LLM omitted an explicit team size from the query.')
                if int(payload['team_size']) != int(explicit_team_size):
                    raise ValueError('LLM team size conflicts with an explicit query value.')

            explicit_pricing = next((canonical for phrase, canonical in PRICING.items() if re.search(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])', query_low)), None)
            allowed_pricing_set = {str(x).lower() for x in allowed_pricing}
            if explicit_pricing and allowed_pricing_set and str(payload.get('pricing_tier') or '').lower() != explicit_pricing.lower():
                raise ValueError('LLM omitted an explicit supported pricing signal from the query.')

            explicit_features = {canonical for canonical, phrases in FEATURE_ALIASES.items() if any(re.search(rf'(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])', query_low) for phrase in phrases) and canonical in {x.lower() for x in allowed_features}}
            extracted_features = {str(x).lower() for x in payload.get('features', [])}
            canonical_feature_map = {x.lower(): x for x in allowed_features}
            missing_features = [canonical_feature_map[x] for x in explicit_features if x not in extracted_features and x in canonical_feature_map]
            if missing_features:
                raise ValueError('LLM omitted an explicit supported feature from the query: ' + ', '.join(missing_features))
            return LLMResult(payload, True, False)
        except Exception as exc:
            return LLMResult(None, False, True, f'LLM requirements validation failed: {exc}')

    async def generate_probes(
        self,
        query: str,
        needs: Dict[str, Any],
        missing_dimensions: Sequence[str],
        vocab: Dict[str, List[str]],
        max_questions: int,
    ) -> LLMResult:
        system = '''Generate only high-impact clarification questions for a software recommendation engine.
Ask no question for a dimension that is already resolved. Only use fields listed in missing_dimensions.
Questions must be concrete and decision-relevant. Return JSON exactly as:
{"probes":[{"field":"...","question":"...","why_it_matters":"...","options":[],"expected_impact":0.0}]}
Never invent option values; options must come from the supplied vocabularies.'''

        user = {
            'query': query,
            'needs': needs,
            'missing_dimensions': list(missing_dimensions),
            'vocab': vocab,
            'max_questions': max_questions,
        }
        result = await self._chat([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(user)},
        ])
        if not result.used_api or not result.data:
            return result
        try:
            rows = result.data.get('probes')
            if not isinstance(rows, list):
                raise ValueError('probes must be a list')
            valid = []
            seen_fields = set()
            allowed_fields = set(missing_dimensions)
            for row in rows[:max_questions * 2]:
                if not isinstance(row, dict) or row.get('field') not in allowed_fields:
                    continue
                field = row['field']
                if field in seen_fields:
                    continue
                options = row.get('options', [])
                if not isinstance(options, list):
                    options = []
                vocab_key = {'category': 'categories', 'pricing_tier': 'pricing'}.get(field, field)
                allowed_options = {str(x).lower(): x for x in vocab.get(vocab_key, [])}
                options = [allowed_options[str(x).lower()] for x in options if str(x).lower() in allowed_options]
                valid.append({
                    'field': field,
                    'question': str(row.get('question') or '').strip(),
                    'why_it_matters': str(row.get('why_it_matters') or '').strip(),
                    'options': options[:8],
                    'expected_impact': max(0.0, min(1.0, float(row.get('expected_impact') or 0))),
                })
                seen_fields.add(field)
            valid = [x for x in valid if x['question'] and x['why_it_matters']][:max_questions]
            if not valid:
                raise ValueError('No valid API-generated probes remained after validation.')
            return LLMResult({'probes': valid}, True, False)
        except Exception as exc:
            return LLMResult(None, False, True, f'LLM probe validation failed: {exc}')

    async def rerank(
        self,
        query: str,
        needs: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        top_k: int,
    ) -> LLMResult:
        if not candidates:
            return LLMResult(None, False, True, 'No candidates available for reranking.')
        system = '''You are a ranking assistant inside a grounded software recommender.
Reorder ONLY the supplied candidate product IDs. Do not add, remove, or invent products.
Prioritize explicit requirements and hard constraints; use evidence fields provided for each candidate.
Return JSON exactly as {"ordered_product_ids":["id1","id2",...]} containing EVERY supplied candidate ID exactly once. `top_k` is only used by the caller after validation; do not truncate the candidate list.'''
        user = {
            'query': query,
            'needs': needs,
            'candidates': candidates,
            'top_k': top_k,
        }
        result = await self._chat([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(user)},
        ], temperature=0.02)
        if not result.used_api or not result.data:
            return result
        try:
            ids = result.data.get('ordered_product_ids')
            allowed = [str(c['id']) for c in candidates]
            allowed_set = set(allowed)
            if not isinstance(ids, list):
                raise ValueError('ordered_product_ids must be a list')
            normalized = [str(x) for x in ids]
            if any(pid not in allowed_set for pid in normalized):
                raise ValueError('Reranker returned a product ID outside the supplied candidate pool.')
            if len(normalized) != len(set(normalized)):
                raise ValueError('Reranker returned duplicate product IDs.')
            if set(normalized) != allowed_set:
                raise ValueError('Reranker must return every supplied candidate exactly once.')
            return LLMResult({'ordered_product_ids': normalized}, True, False)
        except Exception as exc:
            return LLMResult(None, False, True, f'LLM rerank validation failed: {exc}')

    @staticmethod
    def _grounded_bullet(text: str, recommendation: Dict[str, Any]) -> bool:
        # A safe explanation must repeat at least one meaningful catalog/evidence token
        # OR an exact multi-word phrase from the supplied evidence. Generic words do not count.
        text_low = str(text).lower()
        sources = [
            str(recommendation.get('product_name', '')),
            *[str(x) for x in recommendation.get('matched_requirements', [])],
            *[str(x) for x in recommendation.get('unmet_requirements', [])],
            *[str(e.get('requirement', '')) for e in recommendation.get('evidence', []) if isinstance(e, dict)],
            *[str(e.get('evidence', '')) for e in recommendation.get('evidence', []) if isinstance(e, dict)],
        ]
        stop = {'this','that','with','from','your','their','product','supports','support','available','because','recommended','recommendation','requirement','requirements','the','and','for','has','have','into','only','what','would','make','better','fit','explicit','matches','match'}
        source_tokens = set()
        phrases = []
        for src in sources:
            toks = [t for t in re.findall(r'[a-z0-9]+', src.lower()) if len(t) >= 3 and t not in stop]
            source_tokens.update(toks)
            if len(toks) >= 2:
                for i in range(len(toks)-1):
                    phrases.append(' '.join(toks[i:i+2]))
        if any(phrase in text_low for phrase in phrases):
            return True
        return any(t in source_tokens for t in re.findall(r'[a-z0-9]+', text_low) if len(t) >= 3)


    async def explain(
        self,
        query: str,
        needs: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
    ) -> LLMResult:
        system = '''Write concise, evidence-grounded explanations for the supplied recommendations.
Use ONLY the supplied product evidence and unmet requirements. Never invent a feature, integration, price, deployment model, or product fact.
Each "why_recommended" bullet MUST include at least one exact value from the evidence: the product name, an integration name (e.g. Slack, Jira), a feature name (e.g. dashboards, pipeline), team size, category, or deployment model.
Each "improve_fit" bullet MUST reference an exact unmet requirement value, OR start with "No explicit gaps" if unmet_requirements is empty.
Return JSON exactly as:
{"recommendations":[{"product_id":"...","why_recommended":["..."],"improve_fit":["..."]}]}
Keep each list to 1-4 short bullets and keep product IDs unchanged.'''
        user = {
            'query': query,
            'needs': needs,
            'recommendations': recommendations,
        }
        result = await self._chat([
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(user)},
        ], temperature=0.04)
        if not result.used_api or not result.data:
            return result
        try:
            rows = result.data.get('recommendations')
            if not isinstance(rows, list):
                raise ValueError('recommendations must be a list')
            valid = []
            allowed_ids = {str(x['product_id']) for x in recommendations}
            seen = set()
            for row in rows:
                pid = str(row.get('product_id') or '')
                if pid not in allowed_ids or pid in seen:
                    continue
                why = row.get('why_recommended')
                improve = row.get('improve_fit')
                if not isinstance(why, list) or not isinstance(improve, list):
                    continue
                why = [str(x).strip() for x in why[:4] if str(x).strip()]
                improve = [str(x).strip() for x in improve[:4] if str(x).strip()]
                source = next(x for x in recommendations if str(x['product_id']) == pid)
                if not why or not improve:
                    continue
                if not all(self._grounded_bullet(x, source) for x in why):
                    continue
                # Improvement bullets are also constrained: with explicit gaps they
                # must overlap supplied evidence; without gaps only an explicit no-gap
                # statement is accepted, preventing new unsupported recommendations.
                if source.get('unmet_requirements'):
                    if not all(self._grounded_bullet(x, source) for x in improve):
                        continue
                elif not all(self._grounded_bullet(x, source) or x.lower().startswith('no explicit') for x in improve):
                    continue
                valid.append({'product_id': pid, 'why_recommended': why, 'improve_fit': improve})
                seen.add(pid)
            if not valid:
                raise ValueError('API explanation did not safely cover any recommendation.')
            # Partial coverage is acceptable — main.py merges LLM explanations only
            # for products that passed grounding checks; others keep deterministic text.
            return LLMResult({'recommendations': valid}, True, False)
        except Exception as exc:
            return LLMResult(None, False, True, f'LLM explanation validation failed: {exc}')


llm = LLMClient()
