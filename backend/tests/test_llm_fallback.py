import asyncio

from app.core.llm import LLMClient, LLMResult


def test_api_first_requirements_path(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.05):
        return LLMResult({
            'category': 'CRM',
            'team_size': 20,
            'integrations': ['Slack'],
            'features': [],
            'deployment': [],
            'pricing_tier': None,
            'confidence': 0.92,
        }, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM for 20 users with Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api is True
    assert result.fallback is False
    assert result.data['team_size'] == 20


def test_failed_api_returns_fallback_signal(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def failing_chat(messages, temperature=0.05):
        return LLMResult(None, False, True, 'provider timeout')

    monkeypatch.setattr(client, '_chat', failing_chat)
    result = asyncio.run(client.explain('CRM', {}, [{
        'product_id': 'p1',
        'product_name': 'A',
        'matched_requirements': ['CRM'],
        'unmet_requirements': ['Slack'],
        'evidence': [],
    }]))
    assert result.used_api is False
    assert result.fallback is True
    assert 'timeout' in (result.error or '')



def test_api_probe_options_are_checked_against_plural_vocab_keys(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.05):
        return LLMResult({'probes': [
            {'field': 'category', 'question': 'What type?', 'why_it_matters': 'Category partitions the search space.', 'options': ['CRM', 'NOT_A_CATEGORY'], 'expected_impact': 1.0},
            {'field': 'pricing_tier', 'question': 'What pricing level?', 'why_it_matters': 'Pricing changes fit.', 'options': ['$$', 'NOPE'], 'expected_impact': 0.5},
        ]}, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    import asyncio
    result = asyncio.run(client.generate_probes(
        'software', {}, ['category', 'pricing_tier'],
        {'categories': ['CRM', 'Analytics'], 'pricing': ['$', '$$'], 'integrations': [], 'features': [], 'deployment': []}, 3
    ))
    assert result.used_api
    assert result.data['probes'][0]['options'] == ['CRM']
    assert result.data['probes'][1]['options'] == ['$$']



def test_api_requirements_support_negative_integrations(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.05):
        return LLMResult({
            'category': 'CRM',
            'team_size': 20,
            'integrations': ['Slack'],
            'excluded_integrations': ['Slack'],
            'features': [],
            'deployment': [],
            'pricing_tier': None,
            'confidence': 0.9,
        }, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM without Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api
    assert result.data['integrations'] == []
    assert result.data['excluded_integrations'] == ['Slack']


def test_api_requirements_contract_rejects_lossy_explicit_signal(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.05):
        return LLMResult({
            'category': None,
            'team_size': 20,
            'integrations': [],
            'excluded_integrations': [],
            'features': [],
            'deployment': [],
            'pricing_tier': None,
            'confidence': 0.99,
        }, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM for 20 users with Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api is False
    assert result.fallback is True
    assert 'omitted' in (result.error or '').lower()


def test_api_rerank_contract_rejects_unknown_or_missing_ids(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.02):
        return LLMResult({'ordered_product_ids': ['p1', 'not-in-pool']}, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.rerank('CRM', {}, [
        {'id': 'p1'}, {'id': 'p2'}
    ], 2))
    assert result.used_api is False
    assert result.fallback is True
    assert 'outside' in (result.error or '').lower()



def test_api_rerank_rejects_partial_order(monkeypatch):
    client = LLMClient()
    client.enabled = True

    async def fake_chat(messages, temperature=0.02):
        return LLMResult({'ordered_product_ids': ['p2']}, True, False)

    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.rerank('CRM', {}, [{'id': 'p1'}, {'id': 'p2'}, {'id': 'p3'}], 3))
    assert result.used_api is False
    assert result.fallback is True
    assert 'every supplied candidate' in (result.error or '').lower()


def test_api_requirements_rejects_missing_explicit_team_size(monkeypatch):
    import asyncio
    client = LLMClient()
    async def fake_chat(*args, **kwargs):
        return LLMResult({'category': 'CRM', 'team_size': None, 'integrations': ['Slack'], 'excluded_integrations': [], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.9}, True, False)
    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM for 20 users with Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api is False
    assert result.fallback is True
    assert 'team size' in (result.error or '').lower()


def test_api_requirements_rejects_unknown_category(monkeypatch):
    import asyncio
    client = LLMClient()
    async def fake_chat(*args, **kwargs):
        return LLMResult({'category': 'Invented Category', 'team_size': 20, 'integrations': ['Slack'], 'excluded_integrations': [], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.9}, True, False)
    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM for 20 users with Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api is False and result.fallback is True
    assert 'unknown category' in (result.error or '').lower()


def test_api_requirements_rejects_unknown_integration(monkeypatch):
    import asyncio
    client = LLMClient()
    async def fake_chat(*args, **kwargs):
        return LLMResult({'category': 'CRM', 'team_size': 20, 'integrations': ['BogusIntegration'], 'excluded_integrations': [], 'features': [], 'deployment': [], 'pricing_tier': None, 'confidence': 0.9}, True, False)
    monkeypatch.setattr(client, '_chat', fake_chat)
    result = asyncio.run(client.understand('CRM for 20 users with Slack', {}, ['CRM'], ['Slack'], [], [], ['$', '$$', '$$$', '$$$$']))
    assert result.used_api is False and result.fallback is True
    assert 'unknown integrations' in (result.error or '').lower()
