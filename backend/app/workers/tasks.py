import redis 
import json

from rag.service.loader import Loader
from rag.service.emb_model import embed
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

@celery_app.task(bind=True)
def process_uploaded_file(self, document_id: int):

    db = SessionLocal()
    local_path = None
    try:
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document id={document_id} not found")

        local_path = download_to_temp(document.storage_path)
        loader = Loader()
        pages = loader.load_pdf(local_path)
        full_text = "\n".join(page.page_content for page in pages)
        law_name = document.filename.rsplit(".", 1)[0]
        article_nodes = VietnameseLegalParser(law_name=law_name).parse_articles(full_text)
        chunks = chunk_document(article_nodes, law_name=law_name)
        if not chunks:
            chunks = [{"content": full_text, "metadata": {"law": law_name}}]

        enriched_chunks = [
            {
                **chunk,
                "metadata": enrich_chunk_metadata(
                    chunk["content"],
                    chunk.get("metadata", {}),
                ),
            }
            for chunk in chunks
        ]

        # encoder = SentenceTransformer(EMBEDDING_MODEL)
        texts = [chunk["content"] for chunk in enriched_chunks]
        # embeddings = encoder.encode(texts, show_progress_bar=False)
        embeddings = embed(texts)

        for index, (chunk, embedding) in enumerate(zip(enriched_chunks, embeddings)):
            db.add(DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk["content"],
                chunk_metadata=chunk["metadata"],
                embedding=embedding.tolist(),
            ))

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

        return {"status": "ok", "document_id": document.id, "chunks": len(enriched_chunks)}
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
