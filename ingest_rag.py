import asyncio
import os
import sys

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.api.routes.knowledge import SyncKnowledgeRequest, _process_and_embed_document
from app.db import db_service

async def run():
    print("Iniciando vetorização do RAG...")
    try:
        with open("RAG/FAQ_Clinica_Odontologica_RAG.md", "r", encoding="utf-8") as f:
            content = f.read()
        
        payload = SyncKnowledgeRequest(
            source_id="faq_odontologico_mvp",
            source_name="FAQ_Clinica_Odontologica_RAG.md",
            content=content
        )
        
        print("Lendo texto e gerando embeddings (pode levar alguns segundos)...")
        await _process_and_embed_document(payload)
        
        # Check if vectors were inserted
        res = db_service.client.table("faq_vec").select("source_id", count="exact").execute()
        count = res.count if hasattr(res, "count") else len(res.data)
        
        print(f"SUCESSO: Base de conhecimento carregada! Temos agora {count} blocos de conhecimento salvos no Supabase (faq_vec).")
    except Exception as e:
        print(f"ERRO durante a vetorização: {e}")

if __name__ == "__main__":
    asyncio.run(run())
