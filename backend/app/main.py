from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text
# from sentence_transformers import SentenceTransformer
import os

from app.database import engine
from app.models.base import Base
from app.core.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.upload import router as upload_router
from app.routers.chat import router as chat_router
from app.routers.ws import ws_router
from app.services.source.storage_service import ensure_bucket_exists
import app.models


settings = get_settings()
# EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket_exists()
    # print("Đang load model...")
    # app.state.seq = SentenceTransformer(EMBEDDING_MODEL, token = os.getenv("HF_TOKEN"))
    # print("Model đã sẵn sàng")
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
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    conn.execute(text(
        "CREATE OR REPLACE FUNCTION immutable_unaccent(text) "
        "RETURNS text "
        "LANGUAGE sql "
        "IMMUTABLE "
        "PARALLEL SAFE "
        "AS $$ SELECT public.unaccent('public.unaccent', $1) $$"
    ))

Base.metadata.create_all(bind=engine)

with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS chunk_metadata JSON DEFAULT '{}' NOT NULL"
    ))

    conn.execute(text(
        "ALTER TABLE documents "
        "ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES chat_sessions(id)"
    ))

    conn.execute(text(
            "ALTER TABLE chat_messages "
            "ADD COLUMN IF NOT EXISTS token INTEGER DEFAULT 0"
    ))

    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_document_chunks_fts_unaccent "
        "ON document_chunks USING GIN ("
        "to_tsvector('simple', immutable_unaccent(content || ' ' || coalesce(chunk_metadata::text, '')))"
        ")"
    ))


@app.get("/")
def healthy_check():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(ws_router)
