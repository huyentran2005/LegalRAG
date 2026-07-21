from pathlib import Path

from rag.service.loader import Loader
from rag.service.split import TextSplitter
from sentence_transformers import SentenceTransformer
from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.storage_service import download_to_temp, cleanup_temp_file


EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


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
        splitter = TextSplitter()
        chunks = splitter.split(pages)

        encoder = SentenceTransformer(EMBEDDING_MODEL)
        texts = [chunk.page_content for chunk in chunks]
        embeddings = encoder.encode(texts, show_progress_bar=False)

        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk.page_content,
                embedding=list(embedding),
            ))

        document.page_count = len(pages)
        document.status = DocumentStatus.COMPLETED
        db.commit()
        return {"status": "ok", "document_id": document.id, "chunks": len(chunks)}
    except Exception:
        if "document" in locals() and document is not None:
            document.status = DocumentStatus.FAILED
            db.commit()
        raise
    finally:
        if local_path:
            cleanup_temp_file(local_path)
        db.close()
