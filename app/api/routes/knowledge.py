import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.db import db_service

logger = logging.getLogger(__name__)
router = APIRouter()


class SyncKnowledgeRequest(BaseModel):
    source_id: str
    source_name: str
    content: str
    clinic_id: Optional[str] = None


def _safe_db_client():
    try:
        return db_service.client
    except ValueError:
        logger.warning("Supabase credentials are not configured. Skipping vector persistence.")
        return None


async def _process_and_embed_document(payload: SyncKnowledgeRequest) -> None:
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        logger.error("langchain_openai not installed. Cannot generate embeddings.")
        return

    content = payload.content.strip()
    if not content:
        logger.warning(f"Empty content received for source: {payload.source_name}")
        return

    clinic_id = payload.clinic_id or settings.CLINIC_ID_PILOT

    # Split text into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    chunks = text_splitter.create_documents(
        [content], 
        metadatas=[{"source_id": payload.source_id, "source_name": payload.source_name}]
    )

    if not chunks:
        logger.warning("No chunks generated from the content.")
        return

    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not configured. Skipping embedding generation.")
        return

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small", 
        openai_api_key=settings.OPENAI_API_KEY
    )

    try:
        # Generate embeddings for all chunks
        texts = [chunk.page_content for chunk in chunks]
        vectors = await embeddings.aembed_documents(texts)
    except Exception as exc:
        logger.error("Failed to generate embeddings: %s", exc)
        return

    db_client = _safe_db_client()

    # Delete old chunks for this source if it's an update
    if db_client and payload.source_id:
        try:
            db_client.table("faq_vec").delete().eq("source_id", payload.source_id).execute()
        except Exception as exc:
            logger.warning("Failed to delete old vectors for source %s: %s", payload.source_id, exc)

    # Insert new chunks
    records = []
    for chunk, vector in zip(chunks, vectors):
        records.append(
            {
                "clinic_id": clinic_id,
                "source_id": payload.source_id,
                "source_name": payload.source_name,
                "chunk_text": chunk.page_content,
                "embedding": vector,
                "metadata": chunk.metadata,
            }
        )

    if db_client and records:
        try:
            # Batch inserts can be done by inserting the list directly
            db_client.table("faq_vec").insert(records).execute()
            logger.info("Successfully inserted %d vectors for %s", len(records), payload.source_name)
        except Exception as exc:
            logger.error("Failed to insert vectors into faq_vec: %s", exc)


@router.post("/sync")
async def sync_knowledge(payload: SyncKnowledgeRequest, background_tasks: BackgroundTasks):
    """
    Endpoint (Webhook) para receber textos (ex: do Google Drive via Automação/n8n)
    e sincronizar na base vetorial faq_vec.
    """
    if not payload.content.strip():
        raise HTTPException(status_code=422, detail="Content cannot be empty")

    # Schedule the embedding processing in the background
    background_tasks.add_task(_process_and_embed_document, payload=payload)
    
    return {
        "status": "processing",
        "message": f"Document '{payload.source_name}' is being processed and vectorized in the background."
    }
