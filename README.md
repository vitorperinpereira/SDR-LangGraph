# SDR Inteligente Odontologico

MVP de agente SDR para clinica odontologica com atendimento via WhatsApp, qualificacao de lead e semi-agendamento.

## Status Atual

Implementado:

- API FastAPI com `POST /api/webhook` (e rota legada `POST /webhook/evolution`).
- Fluxo conversacional com estados (`qualify`, `collect_preferences`, `waiting_choice`, `done`, `objection`).
- Tratamento de Objeções (preço, medo, distância, etc.) com respostas empáticas.
- Persistencia de lead, conversa e mensagens no Supabase.
- Persistencia de follow-up em `tb_followup` (fallback para `followups`).
- Confirmacao de agendamento no banco e registro de `google_event_id`.
- Validacao de webhook secret por header `x-webhook-secret` (quando configurado).
- Debounce de mensagens com Redis (fallback em memoria).
- Transcricao de audio inbound via OpenAI Audio API (quando configurado).
- Pos-processamento assincrono: Evolution (read/presence/send) e sincronizacao opcional com Google Sheets.
- Integração Google Calendar híbrida (Real se credenciais presentes, Mock caso contrário).

Mockado:

- Disponibilidade de horarios (`app/clinicorp_sim.py`) e simulada.

Planejado:

- Integracao real com Clinicorp.
- Persistencia de checkpoints LangGraph 100% em Postgres em producao.

## Arquitetura

- Backend: Python + FastAPI
- Orquestracao: LangGraph
- Banco: Supabase/Postgres
- Canal: Evolution API (WhatsApp)
- Agenda: Google Calendar

## Estrutura

```text
app/
  main.py
  config.py
  db.py
  services/
    supabase_service.py
    redis_service.py
    evolution_service.py
    audio_service.py
    sheets_service.py
  graph/
    state.py
    workflow.py
    nodes/
      classifier.py
      comercial.py
      agendamento.py
      post_chat.py
    tools/
      kb_retriever.py
      calendar.py
  state.py
  evolution.py
  gcal.py
  clinicorp_sim.py

tests/
  test_graph.py
  test_webhook.py
  test_objection.py

schema.sql
TASKS.md
README.md
Dockerfile
```

## Setup Local

1. Criar e ativar ambiente virtual:

```bash
python -m venv venv
venv\Scripts\activate
```

1. Instalar dependencias:

```bash
pip install -r requirements.txt
```

1. Criar `.env` na raiz:

```env
PROJECT_NAME=SDR Agent Dental
VERSION=0.1.0

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_AUDIO_MODEL=gpt-4o-mini-transcribe
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS=45

SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
REDIS_URL=
REDIS_DEBOUNCE_TTL_SECONDS=30
CLINIC_ID_PILOT=

EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_WEBHOOK_SECRET=

GCAL_CREDENTIALS_JSON=credentials.json
GSHEETS_SPREADSHEET_ID=
GSHEETS_RANGE=Leads!A:I
DATABASE_URL=
```

## Variaveis de Ambiente

| Variavel | Obrigatoria | Descricao |
|---|---|---|
| `SUPABASE_URL` | Sim | URL do projeto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Sim | Chave service role (backend only) |
| `OPENAI_AUDIO_MODEL` | Opcional | Modelo de transcricao de audio (`gpt-4o-mini-transcribe` por padrao) |
| `OPENAI_API_BASE_URL` | Opcional | Base URL da API OpenAI |
| `OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS` | Opcional | Timeout da transcricao de audio |
| `REDIS_URL` | Opcional | URL Redis para debounce distribuido (fallback em memoria se vazio) |
| `REDIS_DEBOUNCE_TTL_SECONDS` | Opcional | TTL padrao do debounce Redis (segundos) |
| `CLINIC_ID_PILOT` | Sim | ID da clinica piloto |
| `EVOLUTION_API_URL` | Sim para envio | Base URL da Evolution API |
| `EVOLUTION_API_KEY` | Sim para envio | API key Evolution |
| `EVOLUTION_WEBHOOK_SECRET` | Recomendado | Segredo validado no header `x-webhook-secret` |
| `DATABASE_URL` | Opcional | Ativa tentativa de checkpointer Postgres |
| `GCAL_CREDENTIALS_JSON` | Opcional | Caminho para JSON da Service Account do Google |
| `GCAL_CREDENTIALS_B64` | Opcional | Conteudo do JSON da Service Account em Base64 (prioridade sobre arquivo) |
| `GCAL_CALENDAR_ID` | Opcional | Calendar ID para criacao de evento (default `primary`) |
| `GSHEETS_SPREADSHEET_ID` | Opcional | Spreadsheet alvo para sync de leads com `muito_interesse` |
| `GSHEETS_RANGE` | Opcional | Range de append no Google Sheets (default `Leads!A:I`) |

Template de producao:

- Use `.env.production.example` como base para configurar variaveis no provedor de deploy.
- Nao commitar `credentials.json` nem valores sensiveis.
- Em deploy, prefira `GCAL_CREDENTIALS_B64` para evitar arquivo fisico.

## Banco de Dados

Execute `schema.sql` no Supabase.

Tabelas principais:

- `clinics`
- `leads`
- `conversations`
- `messages`
- `appointments`
- `checkpoints`

Observacao:

- `appointments` usa `slot_time` (nao `start_time/end_time`).

## Executando

### Localmente

```bash
uvicorn app.main:app --reload
```

Smoke check dos servicos da Fase 1:

```bash
python -m execution.phase1_services_check
```

### Via Docker

```bash
docker build -t sdr-agent .
docker run -p 8000:8000 --env-file .env sdr-agent
```

## Deploy (Checklist Rapido)

1. Configurar variaveis do `.env.production.example` no ambiente de deploy.
2. Garantir que `EVOLUTION_WEBHOOK_SECRET` esteja definido e alinhado com o provedor.
3. Definir `DATABASE_URL` de producao para habilitar tentativa de `PostgresSaver`.
4. Disponibilizar `credentials.json` no ambiente (ou ajustar `GCAL_CREDENTIALS_JSON` para o caminho correto).
   Alternativa recomendada: definir `GCAL_CREDENTIALS_B64` com o conteudo do JSON codificado em Base64.
5. Fazer deploy da imagem Docker e validar `GET /health`.
6. Testar fluxo critico: webhook -> confirmacao -> persistencia de `google_event_id`.

Health check:

- `GET /health`

## Webhook Evolution

Endpoint:

- `POST /api/webhook` (principal)
- `POST /webhook/evolution` (compatibilidade)

Header de seguranca (quando configurado):

- `x-webhook-secret: <EVOLUTION_WEBHOOK_SECRET>`

Payload Evolution (principal):

```json
{
  "data": {
    "pushName": "Carlos",
    "key": { "remoteJid": "5511999999999@s.whatsapp.net" },
    "message": {
      "fromMe": false,
      "conversation": "Meu nome e Carlos, estou com dor."
    }
  }
}
```

Payload simplificado (suporte local):

```json
{
  "from": "5511999999999",
  "body": "Meu nome e Carlos, estou com dor."
}
```

Payload com audio (exemplo):

```json
{
  "data": {
    "pushName": "Carlos",
    "key": { "id": "evt-audio-1", "remoteJid": "5511999999999@s.whatsapp.net" },
    "message": {
      "fromMe": false,
      "audioMessage": { "url": "https://example.com/audio.ogg", "mimetype": "audio/ogg" }
    }
  }
}
```

## Fluxo Conversacional (MVP)

1. `qualify`: coleta nome e motivo.
2. `collect_preferences`: coleta periodo/dia.
3. `waiting_choice`: oferece 2 horarios e captura escolha.
4. `objection`: identifica sentimentos negativos (caro, medo, etc.) e responde com empatia.
5. `done`: backend registra appointment + evento calendar (mock ou real).

## Persistencia de Estado (LangGraph)

- Sem `DATABASE_URL`: `MemorySaver`.
- Com `DATABASE_URL`: tenta `PostgresSaver`; em erro, fallback para `MemorySaver`.

## Testes

Rodar:

```bash
python -m pytest
```

Smoke check da Fase 2:

```bash
python -m execution.phase2_graph_check
```

Cobertura atual de comportamento:

- Transicoes principais do grafo.
- Tratamento de objeções.
- Validacao de secret do webhook.
- Processamento de payload simplificado e confirmacao de agendamento.

## Seguranca

- Secret do webhook validado no backend.
- Service role key usada somente no servidor.
- Logs de webhook com `thread_id` para correlacao operacional.
- Mascaramento basico de PII em logs (telefone e sequencias numericas longas).
- Idempotencia de webhook em memoria por `provider_event_id` (janela TTL de 10 min).
- Recomenda-se adicionar rate limit por origem e evoluir idempotencia para storage compartilhado em multi-instancia.

## Backlog

Roadmap priorizado com criterios de aceite em `TASKS.md`.
