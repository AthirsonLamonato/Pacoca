# Performance e Latência

Este documento descreve o projeto legado a partir da seção seguinte. Para a aplicação desktop recriada em `src/pacoca`, consulte [Usar a Paçoca](USAR-PACOCA.md). Desde a 1.3, o reconhecimento padrão é Whisper base int8, em processo de um thread com teto de CPU de 10% do computador e liberação por inatividade. Whisper small continua opcional em Configurações. Pedidos explícitos, como “abre o Spotify”, usam a ação direta sem carregar o modelo de conversa; aplicativos conhecidos já abertos dispensam a consulta ao menu Iniciar.

`python scripts/check_voice_speed.py` mede o reconhecimento com áudio sintético, testa a seleção de voz e verifica que ruído não cancela uma ação. `--exe dist/Pacoca/Pacoca.exe` repete no executável distribuído. Não captura o microfone humano nem abre aplicativos externos. O tempo total também depende do término da fala, da inicialização do processo e do aplicativo solicitado; um resultado sintético não comprova a latência percebida em um microfone real.

> Guia para diagnosticar lentidão e tunar o Paçoca em hardware modesto (CLAUDE.md
> exige que o projeto rode em 4GB RAM, CPU sem GPU).

---

## Visão geral do pipeline e onde o tempo é gasto

```
comando do usuário
   │
   ├─ Camada 1: regex (ROUTES)         < 1ms   — sempre tentada primeiro
   ├─ Camada 2: TF-IDF (classify_local) ~1-5ms  — scikit-learn, sem rede
   └─ Camada 3: LLM agentic loop       50ms-5s  — Groq (rede) ou Ollama (CPU local)
```

A maior fonte de latência é, de longe, a camada 3. Se um comando comum está lento,
o primeiro passo é confirmar em qual camada ele está caindo — comandos que deveriam
bater em ROUTES (regex) e estão demorando segundos provavelmente têm um regex que
não casa e estão escorregando para o LLM.

---

## Diagnosticando qual camada um comando usa

```python
from core.orchestrator import ROUTES
import re

comando = "abre o spotify"
for pattern, target, _ in ROUTES:
    if re.search(pattern, comando, re.IGNORECASE):
        print("Bateu em ROUTES (camada 1):", pattern, "→", target)
        break
else:
    print("Não bateu em ROUTES — vai para camada 2/3 (TF-IDF / LLM)")
```

Para ver os tempos reais por etapa de um comando específico, consulte
`core/telemetry.py` — cada execução grava `latency_s`, `route`, `tool` e `provider`
em `_command_log` (deque em memória, até 500 entradas), exposto em
`GET /api/metrics` no dashboard.

---

## Latência de LLM

**Groq (online)**: normalmente 200ms–1.5s para `llama-3.1-8b-instant`. Se estiver
consistentemente lento:
- Confirme `GROQ_MODEL` no `.env` — modelos maiores (`70b`) são mais lentos.
- Verifique se o circuit breaker está aberto (3 falhas consecutivas → 120s de
  pausa, ver [troubleshooting.md](troubleshooting.md#llm--ia-groq-ollama)).

Toda chamada HTTP a Groq/Ollama/clima/finanças/busca reutiliza um único
`requests.Session` com pool de conexões (4 conexões, 8 no máximo simultâneas —
`core/providers.py:_get_session()`), evitando o custo de handshake TCP/TLS repetido
em comandos sucessivos.

**Ollama (offline, CPU)**: depende inteiramente do hardware. Em CPU sem GPU,
modelos de 7-8B levam vários segundos por resposta. Para hardware modesto (4GB RAM):
- Use `phi3` ou `llama3:8b-instruct-q4_0` (quantizado) em vez de modelos maiores.
- `ollama run <modelo> --verbose` mostra tokens/s — útil para comparar modelos.
- Evite rodar Ollama e o overlay/STT (Whisper) ao mesmo tempo em CPUs de 4 núcleos
  ou menos; eles competem por CPU.

---

## Cache: onde já existe e como ele ajuda

| Cache | Local | TTL | O que evita |
|---|---|---|---|
| `_intent_cache` | `modules/intent.py` | 300s | Re-rodar TF-IDF + LLM para o mesmo comando repetido |
| `_weather_cache` | `core/providers.py` (`_TTLCache`) | 600s | Chamada de API de clima repetida |
| `_finance_cache` | `core/providers.py` | 120s | Chamada de API de cotação repetida |
| `_search_cache` | `core/providers.py` | 300s | Busca DuckDuckGo repetida |

O cache de intenção (`_intent_cache`) só armazena resultados com `calls` não-vazio —
uma classificação que falhou nunca é cacheada, para permitir nova tentativa
imediata na próxima vez que o usuário repetir o comando (ex: depois de corrigir o
áudio/texto).

**Não há atualmente estatística de hit-rate exposta.** Se for instrumentar isso,
adicione um contador simples em `_cache_get`/`_cache_set` (`modules/intent.py`) e
exponha via `core/telemetry.py`, seguindo o padrão já usado para métricas de
comando.

---

## SQLite

Índices em `ts`/`started_at` já existem (`storage/db.py:init()`) para acelerar
`ORDER BY` e a limpeza por data (`cleanup_old_data`). Para um histórico muito grande
(> 100k linhas), rode `VACUUM` periodicamente — não é feito automaticamente:

```python
import sqlite3
sqlite3.connect("data/pacoca.db").execute("VACUUM")
```

---

## Janela de desktop / UI

A janela de desktop (PyQt6, `output/overlay.py`) roda na thread principal;
o loop de texto/voz do terminal roda numa thread separada — nenhum dos dois
deve bloquear o outro. Comandos digitados ou falados na própria janela
(caixa de texto, botão de microfone) também disparam uma thread de fundo
própria antes de chamar `Orchestrator.dispatch_chain()`, para a chamada ao
Groq/Ollama não travar a UI. Se a janela parecer travada durante um comando
longo, confirme que essa chamada está mesmo saindo em background — veja
`_dispatch_command()`/`_on_submit_text()`/`_on_mic_clicked()` em
`output/overlay.py`.

---

## Dashboard web

- As páginas usam polling htmx (8-20s) em vez de WebSocket para os fragmentos de
  status/histórico — suficiente para um dashboard local, evita reimplementar
  invalidação de cache no servidor.
- O heartbeat de WebSocket (`/ws/command`, `/ws/events`) usa ping a cada 30s e
  fecha a conexão após 90s sem resposta, para não acumular sockets mortos quando o
  laptop hiberna ou a aba fica em background por muito tempo.

---

## Checklist rápido para hardware de 4GB RAM / sem GPU

- [ ] `ai.provider: ollama` com modelo quantizado (`q4_0` ou menor)
- [ ] `stt.model: base` (não `medium`/`large`) em `faster-whisper`
- [ ] `wake_word.enabled: false` + push-to-talk, se a detecção contínua consumir
      CPU demais
- [ ] Evitar rodar transcrição de reunião + STT contínuo + LLM local ao mesmo tempo
