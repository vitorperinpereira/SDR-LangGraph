import logging
from typing import Optional

from langchain_core.tools import tool

from app.services.supabase_service import db_service

logger = logging.getLogger(__name__)


@tool("kb_gmv")
def kb_gmv(query: str, clinic_id: Optional[str] = None, top_k: int = 3) -> str:
    """Busca contexto comercial/FAQ no Supabase para responder duvidas do lead."""
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return "Nao recebi pergunta para consultar a base."

    if not db_service.url or not db_service.service_role_key:
        return "Base de conhecimento indisponivel no momento."

    try:
        safe_top_k = max(1, min(int(top_k), 10))
        query_builder = db_service.client.table("faq_vec").select("*").limit(safe_top_k)
        if clinic_id:
            query_builder = query_builder.eq("clinic_id", clinic_id)
        response = query_builder.execute()
        rows = response.data or []
        if not rows:
            return "Nao encontrei artigos relacionados na base."

        snippets = []
        for row in rows:
            content = row.get("chunk_text") or row.get("content") or row.get("text") or ""
            snippet = " ".join(str(content).split())
            if snippet:
                snippets.append(snippet[:220])

        if not snippets:
            return "Nao encontrei trechos uteis na base."
        return "\n".join(f"- {snippet}" for snippet in snippets[:safe_top_k])
    except Exception as exc:
        logger.warning("kb_gmv fallback due to error: %s", exc)
        return "Nao foi possivel consultar a base agora, mas posso continuar o atendimento normalmente."
