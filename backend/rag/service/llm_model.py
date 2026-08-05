from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_llm(provider: str = "gemini-2.5-flash"):
    if provider and provider.startswith("gemini"):
        if not os.getenv("GEMINI_API"):
            raise RuntimeError("GEMINI_API is required for Gemini provider.")
        llm = ChatGoogleGenerativeAI(
            temperature = 0.2,
            model = os.getenv("GEMINI_MODEL", provider),
            google_api_key = os.getenv("GEMINI_API")
        )
    else:
        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST", "http://ollama:11434"),
            temperature=0.2,
            keep_alive="30m",
            num_ctx=_env_int("OLLAMA_NUM_CTX", 2048),
            num_predict=_env_int("OLLAMA_NUM_PREDICT", 512),
            sync_client_kwargs={"timeout": _env_float("OLLAMA_TIMEOUT", 180.0)},
        )
    return llm
    
