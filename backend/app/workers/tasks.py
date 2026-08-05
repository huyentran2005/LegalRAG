import redis 
import json
import logging
import os

from rag.service.loader import Loader
from rag.service.emb_model import embed_batched
from rag.service.parser import VietnameseLegalParser
from rag.service.chunker import chunk_document
from rag.service.enrichment import enrich_chunk_metadata
# from sentence_transformers import SentenceTransformer
from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.storage_service import download_to_temp, cleanup_temp_file


# EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
settings = get_settings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)
logger = logging.getLogger(__name__)
EMBEDDING_BATCH_SIZE = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", "8")))

@celery_app.task(bind=True)
def process_uploaded_file(self, document_id: int):

    db = SessionLocal()
    local_path = None
    try:
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document id={document_id} not found")

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        document.status = DocumentStatus.PROCESSING
        db.commit()

        logger.info("Processing document id=%s filename=%s", document.id, document.filename)
        local_path = download_to_temp(document.storage_path)
        loader = Loader()
        pages = loader.load_file(local_path, document.filename)
        logger.info("Loaded document id=%s pages=%s", document.id, len(pages))

        full_text = "\n".join(page.page_content for page in pages)
        law_name = document.filename.rsplit(".", 1)[0]
        article_nodes = VietnameseLegalParser(law_name=law_name).parse_articles(full_text)
        chunks = chunk_document(article_nodes, law_name=law_name)
        if not chunks:
            chunks = [{"content": full_text, "metadata": {"law": law_name}}]
        logger.info("Chunked document id=%s chunks=%s", document.id, len(chunks))

        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start:start + EMBEDDING_BATCH_SIZE]
            texts = [chunk["content"] for chunk in batch]
            embeddings = embed_batched(texts, batch_size=EMBEDDING_BATCH_SIZE)

            for offset, (chunk, embedding) in enumerate(zip(batch, embeddings)):
                db.add(DocumentChunk(
                    document_id=document.id,
                    chunk_index=start + offset,
                    content=chunk["content"],
                    chunk_metadata=enrich_chunk_metadata(
                        chunk["content"],
                        chunk.get("metadata", {}),
                    ),
                    embedding=embedding.tolist(),
                ))
            db.flush()

        document.page_count = len(pages)
        document.status = DocumentStatus.COMPLETED
        db.commit()

        redis_client.publish(
            f"document_status:{document.owner_id}",
            json.dumps({
                "document_id": document.id,
                "status": "COMPLETED",
            })
        )

        return {"status": "ok", "document_id": document.id, "chunks": len(chunks)}
    except Exception:
        if "document" in locals() and document is not None:
            document.status = DocumentStatus.FAILED
            db.commit()
            redis_client.publish(
                f"document_status:{document.owner_id}",
                json.dumps({
                    "document_id": document.id,
                    "status": "FAILED",
                })
            )
        raise
    finally:
        if local_path:
            cleanup_temp_file(local_path)
        db.close()
