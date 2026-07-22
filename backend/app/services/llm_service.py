from functools import lru_cache

import time
import typing
import requests

from app.core.config import get_settings
from rag.service.model_llm import get_hf_llm # type: ignore


def _invoke_llm(llm, prompt: str) -> str:
    if hasattr(llm, "invoke"):
        return llm.invoke(prompt)
    if callable(llm):
        return llm(prompt) # type: ignore
    raise TypeError(f"LLM object {type(llm).__name__} is neither callable nor invoke() capable")


def _post_with_retry(url: str, max_attempts: int = 5, backoff_base: float = 1.0, **kwargs) -> requests.Response:
    attempt = 1
    while True:
        try:
            resp = requests.post(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            status = None
            if e.response is not None:
                status = getattr(e.response, "status_code", None)
            if attempt >= max_attempts or status not in (429, 500, 502, 503, 504):
                raise
            sleep = backoff_base * (2 ** (attempt - 1))
            time.sleep(min(sleep, 60))
            attempt += 1
        except requests.exceptions.RequestException:
            if attempt >= max_attempts:
                raise
            sleep = backoff_base * (2 ** (attempt - 1))
            time.sleep(min(sleep, 60))
            attempt += 1


class GrokLLM:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        temperature: float,
        max_new_tokens: int,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens

    def __call__(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_new_tokens,
        }

        resp = _post_with_retry(url, headers=headers, json=payload, timeout=120)
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class GeminiLLM:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        temperature: float,
        max_new_tokens: int,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_new_tokens = max_new_tokens

    def __call__(self, prompt: str) -> str:
        url = f"{self.base_url}/models/{self.model_name}:generateContent"
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_new_tokens,
            },
        }

        try:
            resp = _post_with_retry(url, params=params, headers=headers, json=payload, timeout=120)
            data = resp.json()
            parts = data["candidates"][0]["content"].get("parts", [])
            return "".join(part.get("text", "") for part in parts).strip()
        except requests.exceptions.HTTPError as e:
            status = None
            if e.response is not None:
                status = getattr(e.response, "status_code", None)
            if status == 429:
                settings = get_settings()
                try:
                    hf = get_hf_llm(
                        model_name=settings.llm_model_name,
                        device=settings.llm_device,
                        temperature=settings.llm_temperature,
                        max_new_tokens=settings.llm_max_new_tokens,
                    )
                    return _invoke_llm(hf, prompt)
                except Exception:
                    raise
            raise


@lru_cache(maxsize=1)
def get_llm():
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("LLM_PROVIDER=gemini requires GEMINI_API_KEY.")
        return GeminiLLM(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            model_name=settings.gemini_model_name,
            temperature=settings.llm_temperature,
            max_new_tokens=settings.llm_max_new_tokens,
        )

    if provider == "grok":
        if not settings.xai_api_key:
            raise RuntimeError("LLM_PROVIDER=grok requires XAI_API_KEY.")
        return GrokLLM(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            model_name=settings.xai_model_name,
            temperature=settings.llm_temperature,
            max_new_tokens=settings.llm_max_new_tokens,
        )

    if provider != "hf":
        raise RuntimeError("LLM_PROVIDER must be one of: hf, grok, gemini.")

    return get_hf_llm()
