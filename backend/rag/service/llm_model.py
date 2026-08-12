from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
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


def get_gemini_api_keys() -> list[str]:
    raw_keys = os.getenv("GEMINI_API_KEYS", "")
    keys = [key.strip() for key in raw_keys.split(",") if key.strip()]
    legacy_key = os.getenv("GEMINI_API")
    if legacy_key and legacy_key.strip() and legacy_key.strip() not in keys:
        keys.append(legacy_key.strip())
    return keys


def get_llm(provider: str = "gemini-3.6-flash", gemini_api_key: str | None = None):
    if provider and provider.startswith("gemini"):
        keys = get_gemini_api_keys()
        api_key = gemini_api_key or (keys[0] if keys else None)
        if not api_key:
            raise RuntimeError("GEMINI_API_KEYS or GEMINI_API is required for Gemini provider.")
        llm = ChatGoogleGenerativeAI(
            temperature = 0.2,
            model = os.getenv("GEMINI_MODEL", provider),
            google_api_key = api_key
        )
    elif provider.lower().startswith("qwen2.5"):
        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST", "http://ollama:11434"),
            temperature=0.2,
            keep_alive="30m",
            num_ctx=_env_int("OLLAMA_NUM_CTX", 2048),
            num_predict=_env_int("OLLAMA_NUM_PREDICT", 512),
            sync_client_kwargs={"timeout": _env_float("OLLAMA_TIMEOUT", 180.0)},
        )
    elif provider.lower().startswith("gpt-4o"):
        llm = ChatOpenAI(
            model= "openai/gpt-4o",
            api_key=str(os.getenv("PROXYLLM_API_KEY")), # type: ignore
            base_url= str(os.getenv("PROXYLLM_BASE_URL")),
            temperature=0.2,
        )
    return llm
    
