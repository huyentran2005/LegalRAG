import os
from rag.service.answer_parser import OfficeRAG



def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _is_ollama_provider(provider: str | None) -> bool:
    return not provider or not provider.startswith("gemini")

def _llm_text(raw) -> str:
    return OfficeRAG._extract_text(raw).strip()


def _is_quota_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "resource_exhausted" in text or "quota exceeded" in text or "429" in text


def _fallback_provider() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

