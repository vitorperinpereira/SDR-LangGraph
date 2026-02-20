---
description: Adaptacao do Fluxo N8N SDR para LangGraph
---

# Overview
O objetivo é migrar o fluxo atual de atendimento de SDR Odontológico do n8n para uma arquitetura baseada em LangGraph e FastAPI (Python). O fluxo envolve recebimento de webhooks do Chatwoot/Evolution API, transcrição de áudio, gestão de contexto no Supabase, classificação de intenção, IA prestando atendimento (RAG) e IA de agendamentos (Google Calendar), além de processamento assíncrono para qualificação do lead e sincronização com Google Sheets.

# Project Type
**BACKEND**

# Tech Stack
- **Framework Principal:** FastAPI (Roteamento de Webhooks, Endpoints APIRest)
- **Orquestração de Agentes:** LangGraph (StateGraph, Conditional Edges, Checkpointers para memória)
- **LLM & Tools:** LangChain / OpenAI API (GPT-4o / GPT-4o-mini / text-embedding-3-small)
- **Banco de Dados & RAG:** Supabase (Postgres, pgvector para o Knowledge Base e histórico do lead)
- **Memória Temporária / Cache:** Redis (Debounce de mensagens / Lock distribuído)
- **Integração WhatsApp:** Evolution API
- **Agendamentos:** Google Calendar API

# File Structure
```
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── webhook.py        # Recebimento Chatwoot/Evolution
│   │   │   └── drive_sync.py     # Sincronização Google Drive -> Supabase
│   ├── core/
│   │   ├── config.py           # Configurações de ambiente
│   │   └── security.py        
│   ├── services/
│   │   ├── audio.py              # Transcrição via OpenAI Whisper
│   │   ├── redis_service.py      # Gestor de debounce
│   │   ├── supabase_service.py   # CRUD Leads, Histórico
│   │   ├── chatwoot.py           # API Chatwoot (Verificar assumido pelo humano)
│   │   ├── evolution.py          # Envio de mensagens e status de leitura
│   │   └── sheets.py             # Integração com Google Sheets
│   ├── graph/
│   │   ├── state.py              # Tipagem do Estado do LangGraph (TypedDict)
│   │   ├── nodes/
│   │   │   ├── classifier.py     # Nó Recepcionista (Intenção)
│   │   │   ├── comercial.py      # Nó Assistente Comercial (RAG Tool)
│   │   │   ├── agendamento.py    # Nó Secretaria (Calendar Tools)
│   │   │   └── post_chat.py      # Nó Classificador de Interesse (Supabase Update)
│   │   ├── tools/
│   │   │   ├── kb_retriever.py   # Busca PGVector
│   │   │   └── calendar.py       # Google Calendar Tools
│   │   └── workflow.py           # Grafo principal compilando a lógica
└── requirements.txt
```

# Task Breakdown

### Fase 1: Setup da Infraestrutura e Casos de Uso Base
- [x] **Task 1: Setup Inicial do FastAPI e Dependências**
  - **Agent:** `backend-specialist`
  - **Input:** Configurar ambiente, `.env`, Supabase Client, Redis Client, LangChain/LangGraph.
  - **Output:** Servidor rodando com dependências instaladas.
  - **Verify:** Instalar requirements e ligar projeto via `uvicorn`. Endpoint de `/health` respondendo 200 OK. 

- [x] **Task 2: Configuração dos Serviços Auxiliares (Redis, Supabase, Evolution)**
  - **Agent:** `backend-specialist`
  - **Input:** Criar funções genéricas de `redis_service` (debounce), banco de dados `supabase_service` e envio na api Evolution.
  - **Output:** Classes de serviço conectadas e isoladas com testes simples.
  - **Verify:** Chamar funções em um `__main__` teste para confirmar injeção de dependências e conexão válidas.

### Fase 2: Configuração do Grafo (LangGraph)
- [x] **Task 3: Definição do StateGraph (state.py)**
  - **Agent:** `backend-specialist`
  - **Input:** Criar dicionário de estado com mensagens, histórico, estado atual do lead, intenção, e output gerado.
  - **Output:** Classe `GraphState` tipada via `TypedDict` em Python 3.10+.
  - **Verify:** Executar verificador de tipos (mypy localmente).

- [x] **Task 4: Criação das Ferramentas da IA (Tools)**
  - **Agent:** `backend-specialist`
  - **Input:** Implementar tool de busca Supabase PGVector (`kb_gmv`) e tools do Google Calendar (Buscar eventos, criar evento).
  - **Output:** Funções anotadas com `@tool`.
  - **Verify:** Invocar tools isoladamente com inputs manuais para validar o retorno claro das agendas e dados RAG.

- [x] **Task 5: Implementação dos Nós Inteligentes (Nodes)**
  - **Agent:** `backend-specialist`
  - **Input:** 
    1. `classifier_node`: Prompt Recepcionista para identificar intenção com output de schema Pydantic.
    2. `comercial_node`: Agente Athena de Comercial + bind de RAG tools.
    3. `agendamento_node`: Agente de Agenda Athena + bind de Calendar tools.
    4. `interesse_node`: Extrai "chatResumo" e "interesse".
  - **Output:** Nós com assinatura `(state: GraphState) -> GraphState` rodando o processamento do langchain.
  - **Verify:** Disparar um invoke de simulação chamando node a node via código para validação de contexto e regras (sys prompt).

- [x] **Task 6: Orquestração do Workflow Principal (workflow.py)**
  - **Agent:** `backend-specialist`
  - **Input:** Ligar os nós e configurar arestas condicionais (`add_conditional_edges`). Configurar o MemorySaver (Postgres checkpointer).
  - **Output:** O grafo de diálogo pronto para uso com o checkpointer assíncrono configurado via Supabase ou PostgreSQL cru.
  - **Verify:** Gerar o PNG do grafo chamando `app.get_graph().draw_mermaid_png()`.

### Fase 3: Integrações de Borda (API & Webhooks)
- [x] **Task 7: Endpoint Webhook de Entrada & Debounce**
  - **Agent:** `backend-specialist`
  - **Input:** Rota `/api/webhook` recebendo dados da Evolution, transcrevendo áudio se necessário (Whisper), aplicando debounce (Redis).
  - **Output:** Controlador que converte o json evolution -> formato State e dispara o Langgraph com ID de Thread.
  - **Verify:** Testar no Postman simulando o exato payload que a Evolution ou Chatwoot encaminha.

- [x] **Task 8: Ações Pós-Atendimento e Google Sheets**
  - **Agent:** `backend-specialist`
  - **Input:** Após o retorno do Langgraph (invoke return), engatilhar assincronamente (background_task) a mensageria na Evolution e salvar preenchimento da `tb_followup`. Se `interesse == muito_interesse`, sincronizar ao Planilhas Google.
  - **Output:** Lead salvo com métricas precisas.
  - **Verify:** Verificar se a Google Sheet recebeu a nova linha e confirmar disparo da Evolution de quebra de leitura e resposta digitada.

### Fase 4: Automação RAG Extra
- [ ] **Task 9: Sincronização Google Drive -> Supabase Vector**
  - **Agent:** `backend-specialist`
  - **Input:** Endpoint para receber webhooks do Google Drive de arquivo alterado/novo. Faz parse de texto, split, embed e upsert no `faq_vec` (Supabase).
  - **Output:** Rotina de sync funcional.
  - **Verify:** Executar request de notificação simulando drive e confirmar embeddings salvos no supabase via consulta sql simples.

# Phase X: Verification
Após a conclusão de todas as fases os testes devem passar:
## ✅ PHASE X COMPLETE
- Lint: [ ] Pass
- Security: [ ] No critical issues (security_scan.py)
- Build/Dev: [ ] Success
- Tests: [ ] RAG Querys e Call tools OK
- Date: Pendente
