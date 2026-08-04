from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
import os

def get_llm(provider: str = "gemini-2.5-flash"):
    if provider == "gemini-3.5-flash":
        llm = ChatGoogleGenerativeAI(
            temperature = 0.2,
            model = "gemini-3.5-flash",
            google_api_key = os.getenv("GEMINI_API")
        )
    else:
        llm = ChatOllama(
            model ="qwen2.5:3b",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            temperature=0.2,
            keep_alive="30m",
            sync_client_kwargs={"timeout": 60.0},
        )
    return llm
    
