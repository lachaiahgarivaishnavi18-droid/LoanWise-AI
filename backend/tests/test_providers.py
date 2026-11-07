"""Transport contract tests only; these do not represent live external connections."""
import asyncio
import json
import httpx
import pytest
from app.config import settings
from ai import providers


@pytest.mark.parametrize('provider',['local-api','openai-compatible','gemini','anthropic'])
def test_provider_transport_contract(provider,monkeypatch):
    monkeypatch.setattr(settings,'llm_provider',provider)
    monkeypatch.setattr(settings,'llm_model','synthetic-contract-model')
    monkeypatch.setattr(settings,'llm_api_key','' if provider=='local-api' else 'unit-test-not-a-secret')
    monkeypatch.setattr(settings,'llm_base_url','http://local.test/v1')
    def respond(request):
        body=json.loads(request.content)
        if provider=='anthropic':
            assert request.headers['x-api-key']=='unit-test-not-a-secret'
            assert body['messages'][0]['content']=='Synthetic test prompt'
            return httpx.Response(200,json={'content':[{'text':'Contract response'}]})
        if provider=='gemini':
            assert request.headers['x-goog-api-key']=='unit-test-not-a-secret'
            assert body['contents'][0]['parts'][0]['text']=='Synthetic test prompt'
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'Contract response'}]}}]})
        assert request.url.path=='/v1/chat/completions'
        assert body['model']=='synthetic-contract-model'
        if provider=='local-api':
            assert 'authorization' not in request.headers
        return httpx.Response(200,json={'choices':[{'message':{'content':'Contract response'}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    assert asyncio.run(providers.generate('Synthetic test prompt'))=='Contract response'
