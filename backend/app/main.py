from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text
from sentence_transformers import SentenceTransformer


from rag.service.model_llm import get_hf_llm
from app.database import engine
from app.models.base import Base
from app.core.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.upload import router as upload_router
from app.routers.chat import router as chat_router
from app.routers.ws import ws_router
from app.services.storage_service import ensure_bucket_exists
import app.models


settings = get_settings()
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket_exists()
    print("Đang load ...")
    app.state.llm = get_hf_llm() 
    app.state.seq = SentenceTransformer(EMBEDDING_MODEL)
    print("Model đã sẵn sàng")
    yield


app = FastAPI(
    title="LegalRAG API",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

Base.metadata.create_all(bind=engine)


@app.get("/")
def healthy_check():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(ws_router)