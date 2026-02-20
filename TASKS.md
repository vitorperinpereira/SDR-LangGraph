# Tasks e Backlog

## P0 (critico)

### P0-01 Corrigir e estabilizar fluxo de estados

Descricao:

- Garantir progresso consistente entre `qualify`, `collect_preferences`, `waiting_choice` e `done`.

Criterios de aceite:

- Conversa avanca com base no contexto do usuario.
- Escolha valida de horario encerra em `done`.
- Testes automatizados cobrindo transicoes principais.

Status:

- Concluido.

### P0-02 Alinhar persistencia de `appointments` com schema

Descricao:

- Usar `slot_time` conforme `schema.sql`.
- Adicionar update para status `confirmed` e `google_event_id`.

Criterios de aceite:

- Registro de appointment criado sem erro de coluna.
- Confirmacao atualiza status e `google_event_id`.

Status:

- Concluido.

### P0-03 Validacao de webhook secret

Descricao:

- Validar `x-webhook-secret` quando `EVOLUTION_WEBHOOK_SECRET` estiver configurado.

Criterios de aceite:

- Requisicao invalida retorna `401`.
- Requisicao valida continua processamento.

Status:

- Concluido.

## P1 (alto)

### P1-01 Integrar confirmacao com Google Calendar

Descricao:

- Na confirmacao, criar evento e persistir `google_event_id`.
- Implementar integração real com API do Google Calendar.
- Manter fallback para Mock se credenciais estiverem ausentes.

Criterios de aceite:

- Fluxo de `done` chama servico de calendario.
- `google_event_id` salvo no appointment.
- Evento criado no Google Calendar real (se credenciais presentes).

Status:

- Concluido (Implementado suporte a credenciais reais com fallback).

### P1-02 Documentacao de persistencia LangGraph

Descricao:

- Documentar claramente modo `MemorySaver` e fallback de `PostgresSaver`.

Criterios de aceite:

- README descreve comportamento atual sem ambiguidade.

Status:

- Concluido.

### P1-03 Cobertura minima de testes de comportamento

Descricao:

- Incluir testes de grafo e webhook.
- Implementar testes para fluxo de objeções.

Criterios de aceite:

- Testes validam transicoes principais.
- Testes validam tratamento de objeções (preço, medo).
- Testes validam `401` para secret invalido.
- Testes validam processamento e resposta em payload simplificado.

Status:

- Concluido.

### P1-04 Tratamento de Objeções (Novo)

Descricao:

- Identificar intenções negativas (caro, medo, longe) e responder com empatia antes de tentar reagendar.

Criterios de aceite:

- Ao detectar palavras-chave, o agente responde de forma empática.
- Fluxo retorna para coleta de preferências após resposta.

Status:

- Concluido.

## P2 (medio)

### P2-01 Limpeza de scripts de execucao desalinhados

Descricao:

- `execution/check_kit.py` referencia modulos fora do escopo do projeto.

Criterios de aceite:

- Script removido ou atualizado para dependencias reais.
- README inclui instrucoes coerentes com scripts.

Status:

- Concluido.

### P2-02 Hardening operacional

Descricao:

- Melhorar observabilidade, mascaramento de PII e idempotencia de webhook.

Criterios de aceite:

- Logs com correlacao por `thread_id`.
- Mensagens sensiveis mascaradas.
- Tratamento de duplicidade de evento do provedor.

Status:

- Concluido (idempotencia em memoria por `provider_event_id`, logs com `thread_id` e mascaramento de telefone/texto sensivel).

## Próximos Passos (Integração e Deploy)

### Integração Real GCal

- [x] Suporte a `GCAL_CREDENTIALS_B64` e `GCAL_CALENDAR_ID` para deploy sem arquivo físico.
- [ ] Adicionar arquivo `credentials.json` na raiz do projeto (quando disponível).
- [ ] Testar agendamento real.

### Deploy

- [x] Preparar Dockerfile.
- [ ] Configurar variáveis de produção no ambiente de deploy.
