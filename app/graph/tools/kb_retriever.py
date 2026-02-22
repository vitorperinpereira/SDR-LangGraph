import logging
from typing import Optional
from uuid import UUID

from langchain_core.tools import tool

from app.services.supabase_service import db_service
from app.config import settings

logger = logging.getLogger(__name__)


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)

@tool("kb_gmv")
def kb_gmv(query: str, clinic_id: Optional[str] = None, top_k: int = 3) -> str:
    """Busca contexto comercial/FAQ no Supabase para responder duvidas do lead."""
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return "Nao recebi pergunta para consultar a base."

    if not db_service.url or not db_service.service_role_key:
        return "Base de conhecimento indisponivel no momento."

    try:
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.OPENAI_API_KEY
        )
        query_embedding = embeddings.embed_query(cleaned_query)
    except Exception as exc:
        logger.warning("Falha ao gerar embedding para a query: %s", exc)
        return "Nao foi possivel processar a consulta neste momento."

    try:
        safe_top_k = max(1, min(int(top_k), 10))
        
        # Bring back up to 500 chunks to do local similarity search
        query_builder = db_service.client.table("faq_vec").select("chunk_text, embedding").limit(500)
        if clinic_id and _is_valid_uuid(clinic_id):
            query_builder = query_builder.eq("clinic_id", clinic_id)
        elif clinic_id:
            logger.info("Ignoring clinic_id filter for kb_gmv because it is not a UUID: %s", clinic_id)
        
        response = query_builder.execute()
        rows = response.data or []
        
        if not rows:
            return "Nao encontrei artigos relacionados na base."

        # Compute similarities
        scored_rows = []
        for row in rows:
            embedding_str_or_list = row.get("embedding")
            if not embedding_str_or_list:
                continue
                
            # Parse embedding if it's a string from Postgres
            import json
            if isinstance(embedding_str_or_list, str):
                vec = json.loads(embedding_str_or_list)
            else:
                vec = embedding_str_or_list
                
            score = _cosine_similarity(query_embedding, vec)
            scored_rows.append((score, row))
            
        # Sort descending by score
        scored_rows.sort(key=lambda x: x[0], reverse=True)
        top_rows = [x[1] for x in scored_rows[:safe_top_k]]

        snippets = []
        for row in top_rows:
            content = row.get("chunk_text") or ""
            snippet = " ".join(str(content).split())
            if snippet:
                # Limit size per chunk if needed, but since chunk_size is 1000 let's keep all.
                snippets.append(snippet[:1500])

        if not snippets:
            return "Nao encontrei trechos uteis na base."
        return "\n".join(f"- {snippet}" for snippet in snippets)
    except Exception as exc:
        logger.warning("kb_gmv fallback due to error: %s", exc)
        return "Nao foi possivel consultar a base agora, mas posso continuar o atendimento normalmente."
