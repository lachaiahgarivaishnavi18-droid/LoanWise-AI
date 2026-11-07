"""Optional provider transport. Policy claims remain extractive until semantic validation is configured."""
import httpx
from app.config import settings


async def generate(prompt: str) -> str:
    if settings.llm_provider == 'local':
        raise RuntimeError('Local mode uses the extractive evidence renderer, not an LLM')
    if not settings.llm_model or (settings.llm_provider!='local-api' and not settings.llm_api_key):
        raise RuntimeError('Provider credentials and model must be configured')
    async with httpx.AsyncClient(timeout=45) as client:
        if settings.llm_provider == 'anthropic':
            result = await client.post('https://api.anthropic.com/v1/messages', headers={'x-api-key': settings.llm_api_key, 'anthropic-version': '2023-06-01'}, json={'model': settings.llm_model, 'max_tokens': 800, 'messages': [{'role': 'user', 'content': prompt}]})
            result.raise_for_status()
            return result.json()['content'][0]['text']
        if settings.llm_provider == 'gemini':
            result = await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent', headers={'x-goog-api-key': settings.llm_api_key}, json={'contents': [{'parts': [{'text': prompt}]}]})
            result.raise_for_status()
            return result.json()['candidates'][0]['content']['parts'][0]['text']
        headers={'Authorization': f'Bearer {settings.llm_api_key}'} if settings.llm_api_key else {}
        result = await client.post(settings.llm_base_url.rstrip('/') + '/chat/completions', headers=headers, json={'model': settings.llm_model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0})
        result.raise_for_status()
        return result.json()['choices'][0]['message']['content']
