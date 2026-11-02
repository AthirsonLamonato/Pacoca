# Paçoca

> Assistente pessoal inteligente de desktop — controle por voz ou texto, 100% open-source e gratuito.

![Version](https://img.shields.io/badge/version-v0.6.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-370%20passing-brightgreen)
![CI](https://github.com/AthirsonLamonato/Pacoca/actions/workflows/tests.yml/badge.svg)

Paçoca é um assistente de desktop estilo Jarvis — modular, expansível e capaz de rodar completamente offline em hardware modesto (4 GB RAM, CPU sem GPU).

---

## Instalação

> Ainda não há um instalador `.exe` publicado nas releases do GitHub — os scripts
> `pacoca.spec`/`wizard.spec`/`setup_wizard.py` existem no repositório para build
> local, mas instale a partir do código-fonte por enquanto.

```bash
git clone https://github.com/AthirsonLamonato/Pacoca.git
cd Pacoca
```

**Windows:**
```bat
setup.bat
```

**Linux / Mac:**
```bash
bash setup.sh
```

Ou manualmente:
```bash
pip install -r requirements.txt
pip install fastapi "uvicorn[standard]"
ollama pull qwen3:4b
```

---

## Executar

```bash
# Modo texto — ideal para testar sem microfone
python main.py --mode text --no-tts --no-overlay

# Modo voz (push-to-talk por padrão)
python main.py

# Dashboard web (abre o browser em localhost:7755)
python main.py --web

# Editor de rotinas CLI
python main.py --edit-routines

# Diagnóstico de IA local, Ollama e segurança
python main.py --doctor
```

---

## Funcionalidades

| Módulo | O que faz |
|---|---|
| **STT** | Transcrição via Whisper (`faster-whisper`). Calibração automática de ruído; VAD por energia RMS. Push-to-talk `ctrl+shift+space` por padrão; wake word via openWakeWord (sem API key, modelo customizável) |
| **Janela de desktop** | Interface PyQt6 (`overlay.enabled: true`): histórico de conversa, caixa de texto, botão de microfone (comando de voz único) e botão de conta Google (Calendar/Drive). Toggle: `ctrl+shift+a`. Desabilitada, roda só por texto/voz no terminal |
| **Transcrição** | Captura microfone ou loopback do sistema (Windows: WASAPI · Linux: PulseAudio). Auto-save a cada 5 min |
| **Resumo / IA** | Resumo e explicações via Ollama local, sem custo, com Groq apenas quando configurado explicitamente |
| **Pesquisa** | Roteamento automático: perguntas factuais/atuais → DuckDuckGo + IA; demais → LLM local |
| **Dev tools** | VS Code, abrir arquivo por nome, ir para linha, criar arquivo, git status/log/commit/push/pull/branch, rodar testes, explicar código via IA |
| **Rotinas** | Sequências configuráveis em YAML com condições (`weekday`, `weekend`, `morning`, `afternoon`, `evening`). Suportam `schedule: {time, days}` para disparo **automático**, sem precisar de comando |
| **Briefing diário proativo** | Todo dia, no horário configurado (`briefing.time`), gera sozinho um resumo com clima + agenda + lembretes pendentes + uso do dia anterior — também disponível sob demanda ("bom dia") |
| **Pomodoro** | Timer de foco com notificação e overlay ao término |
| **Produtividade** | Monitoramento de apps via psutil, relatório diário em Markdown. Sugere pausa **proativamente** após uso contínuo sem descanso (`productivity.break_after_min`) |
| **Sistema** | Abrir/fechar apps, volume, brilho, listar processos (Windows + Linux) |
| **Segurança** | Confirmação antes de ações críticas, lista configurável |
| **Backup** | Local automático + Google Drive (opcional, OAuth via wizard) |
| **Perfis** | work / casual / focus / meeting / night — alteráveis por voz em tempo real |
| **Google Calendar** | Ver agenda, criar/editar/apagar eventos (com convidados por e-mail) — CRUD completo, incluindo via raciocínio livre do LLM |
| **Speaker diarization** | Identifica falantes na transcrição (`[Falante 1]`, `[Falante 2]`…) — requer `pyannote.audio` |
| **Plugin system** | Carregamento dinâmico em `plugins/`. Plugin de anotações incluso. Hot-reload por voz |
| **Memória contextual** | Histórico da sessão injetado no prompt do LLM para respostas coerentes |
| **Memória semântica** | Lembra fatos/preferências e busca por *significado* (não só palavra-chave) via embeddings — Gemini (grátis) ou Ollama local |
| **Roteamento que aprende** | Cache semântico (camada 2.5): memoriza o que o LLM resolve e serve paráfrases futuras localmente, sem nova chamada ao LLM — com guard que impede reaproveitar o argumento errado (`semantic_router.*`) |
| **Detector de hábitos** | Observa padrões recorrentes (mesma ação, mesmo horário, vários dias) e sugere virar rotina — sozinho ou sob demanda ("sugestões") |
| **Anáfora / seguimento** | Entende comandos que dependem do turno anterior: "toca de novo", "fecha ele", "e amanhã?", "e em Recife?" |
| **Confiança aprendida** | Após N aprovações seguidas, para de confirmar ações de risco médio; risco alto sempre confirma (`trust.*`) |
| **Lembretes** | Notificações por voz — horário absoluto ("às 15h") ou relativo ("em 30 min") |
| **Clipboard** | Copiar texto/último resultado, ler e limpar área de transferência por voz |
| **OCR de tela** | Lê texto visível via pytesseract. Salva screenshots |
| **Multi-idioma STT** | Troca o idioma de reconhecimento por voz (PT, EN, ES, FR, DE…) |
| **Sumário de reunião** | Sumário estruturado: resumo executivo, decisões, action items e pendências |
| **Dashboard web** | Interface local (FastAPI + htmx + WebSocket) em `localhost:7755` — histórico, lembretes, envio de comandos em tempo real |
| **Editor de rotinas** | CRUD visual de rotinas no dashboard, persistido no `config.yaml` |
| **Obsidian** | Exporta transcrições, sumários e nota diária para qualquer vault Markdown |
| **Comandos encadeados** | "abre o VS Code e depois foco por 25 min" — múltiplos comandos em sequência |
| **Modo reunião auto** | Detecta Zoom/Teams/Slack via psutil; ativa perfil meeting e transcrição automaticamente. Ao fim da reunião, gera e salva o **sumário sozinho** (`meeting_detector.auto_summarize`), sem precisar pedir |
| **TTS profile-aware** | Rate e volume do TTS sincronizados ao trocar perfil |
| **Banco de dados** | SQLite — histórico de comandos, sessões e transcrições |
| **TTS** | edge-tts (Microsoft Neural, padrão, requer internet) com fallback automático para pyttsx3 (100% offline) |
| **WhatsApp** | Envia mensagens via WhatsApp Web (`pywhatkit`, opcional). Composição natural pelo LLM ("pede pro fulano o que ele está fazendo"). **Dupla barreira de segurança**: sempre pede confirmação explícita + só envia para números em `whatsapp.allowed_numbers` (whitelist) |
| **Agente de navegador** | Automação local supervisionada via Playwright opcional: iniciar sessão isolada, navegar em qualquer domínio HTTP/HTTPS, inspecionar páginas, clicar, preencher campos e salvar screenshots. Desativado por padrão; veja [docs/agente-navegador.md](docs/agente-navegador.md) |
| **Planos supervisionados** | Fila local de tarefas com etapas, estados, verificação de resultado e aprovação/rejeição pelo dashboard antes da execução. `agent.require_plan_approval: true` já é o padrão seguro; defina `false` somente se quiser execução direta |

---

## Comandos disponíveis

> Lista completa e sempre atualizada em [docs/comandos.md](docs/comandos.md) ou no
> dashboard web em `/docs` (`python main.py --web`).

### Sistema
```
abre o VS Code
abre o Chrome
fecha o Spotify
volume 70
aumenta o brilho / diminui o brilho
muta o som
lista processos
```

### Transcrição
```
começa a transcrever
começa a transcrever o sistema        ← loopback (áudio do speaker)
para a transcrição
mostra o que foi falado
```

### IA e pesquisa
```
resume o que foi falado
resumo detalhado
explica o que é recursão
pesquisa como funciona decorators em Python
busca na internet o clima de amanhã
```

### Dev tools
```
abre o arquivo main.py
vai para a linha 42
cria arquivo utils.py
explica o arquivo orchestrator.py
commit "feat: nova funcionalidade"
git push / git pull
o que mudou                           ← git status
mostra os últimos commits             ← git log
cria branch feature/nome
branch atual
roda os testes
```

### Rotinas e produtividade
```
modo trabalho
modo foco
fim do dia
executa rotina end_of_day
foco por 25 min                       ← timer Pomodoro
cancela o timer
status do timer
mostra o tempo de uso
relatório de produtividade
relatório diário
tomei uma pausa                       ← reseta o aviso proativo de descanso
```

### Briefing diário
```
bom dia
resumo do dia
briefing
```
> Também dispara sozinho, sem comando, todo dia no horário de `briefing.time`
> (config.yaml). Veja [Autonomia](#autonomia--funcionalidades-proativas).

### Perfis dinâmicos
```
perfil trabalho / perfil work
perfil casual
perfil foco / perfil focus
perfil reunião / perfil meeting
perfil noturno / perfil noite
qual perfil
lista perfis
```

### Google Calendar
```
o que tenho hoje / agenda hoje
próximo evento / próximo compromisso
adiciona reunião amanhã às 14h
adiciona dentista hoje às 10h30
reunião amanhã às 14h com fulano@email.com   ← convida o e-mail mencionado
apaga o evento dentista                      ← pede confirmação
muda a reunião X pra amanhã às 16h           ← via raciocínio do LLM
autoriza calendário                          ← re-autoriza OAuth se necessário
```

### Lembretes
```
me lembra às 15h de reunião
me lembra em 30 minutos de fazer backup
lista lembretes
cancela lembrete 2
cancela lembretes
```

### Clipboard
```
copia o último resultado
copia Python é incrível para o clipboard
lê a área de transferência
limpa o clipboard
```

### OCR / Tela
```
lê o texto na tela
lê a região central
salva screenshot
```

### Contexto e sessão
```
mostra o contexto
limpa o contexto
resume a sessão
resume a reunião
```

### Dashboard web
```
abre o dashboard
inicia a interface web
para o servidor web / fecha o dashboard
```

### Obsidian
```
exporta a transcrição para o obsidian
exporta o sumário para o obsidian
cria a nota diária
exporta as notas para o obsidian
```

### Comandos encadeados
```
abre o VS Code e depois foco por 25 min
começa a transcrever e então ativa o detector de reunião
para a transcrição e em seguida exporta o sumário para o obsidian
```

### Plugins e meta
```
lista plugins
recarrega plugins
ajuda
```

### WhatsApp
```
manda mensagem para fulano dizendo oi, tudo bem?
pede pro fulano o que ele está fazendo            ← LLM compõe a mensagem
```
> ⚠ **Sempre pede confirmação antes de enviar**, e só envia de fato para
> números cadastrados em `whatsapp.allowed_numbers` (whitelist — por padrão,
> só o seu próprio número). Cadastre contatos em `whatsapp.contacts` no
> `config.yaml`. Requer `pip install pywhatkit` e o WhatsApp Web já logado
> no navegador padrão.

### Inteligência adaptativa
```
toca de novo                          ← repete o último comando (anáfora)
fecha ele                             ← fecha o último app aberto
e amanhã?                             ← reaproveita a intenção anterior
sugestões                             ← hábitos detectados → vira rotina
nível de confiança                    ← ações que deixei de confirmar
reseta a confiança
status do cache semântico
```
> O cache semântico aprende sozinho: paráfrases de comandos já resolvidos pelo
> LLM passam a ser atendidas localmente. Veja [docs/configuracao.md](docs/configuracao.md)
> (`semantic_router`, `habits`, `anaphora`, `trust`).

---

## Autonomia — funcionalidades proativas

Além de responder a comandos, o Paçoca age sozinho em segundo plano, sem precisar
que você pergunte:

| Funcionalidade | Como age | Config |
|---|---|---|
| **Rotinas agendadas** | Qualquer rotina pode declarar `schedule: {time: "HH:MM", days: weekday\|weekend\|morning\|afternoon\|evening\|daily}` em `routines:` — uma thread verifica a cada 60s e dispara sozinha, sem comando | exemplo comentado em `core/config.yaml` |
| **Briefing diário** | Gera e notifica, 1x por dia, no horário configurado: clima + agenda do Google Calendar + lembretes pendentes + uso de apps | `briefing.enabled`, `briefing.time` |
| **Sugestão de pausa** | Monitora tempo contínuo sem pausa e notifica proativamente quando excede o limiar; "tomei uma pausa" zera o contador | `productivity.break_after_min` (0 desativa) |
| **Sumário pós-reunião** | Ao detectar o fim de uma chamada (Zoom/Teams/Meet/etc.), para a transcrição e gera o sumário estruturado sozinho, sem precisar pedir "resume a reunião" | `meeting_detector.auto_summarize` |
| **Insight de aprendizado** | Analisa o histórico de uso periodicamente e notifica sozinho quando há um novo insight (apps mais usados, taxa de sucesso, vocabulário aprendido) | `learner.proactive_enabled`, `learner.interval_hours` |
| **Sugestão de hábito** | Detecta padrões recorrentes (mesma ação, mesmo horário, vários dias) e sugere sozinho virar rotina — cada sugestão só uma vez | `habits.enabled`, `habits.min_days`, `habits.interval_hours` |
| **Detector de reunião** | Já existente: ativa perfil `meeting` e inicia transcrição automaticamente ao detectar a chamada | `"ativa detector de reunião"` |
| **Lembretes** | Já existente: thread de fundo dispara notificação no horário marcado | — |
| **Backup diário** | Já existente: agenda backup local/Drive no horário configurado | `backup.*` |

Todos os agendadores (`modules/routines.py:start_scheduler`, `modules/briefing.py:start_scheduler`,
`modules/learner.py:start_scheduler`, `modules/habits.py:start_scheduler`) são iniciados
automaticamente no boot do `main.py`, junto do rastreamento de produtividade — não exigem
nenhum flag adicional.

### Ações que saem do PC (ex: WhatsApp) são tratadas diferente

Proatividade é só para ações *internas e reversíveis* (notificar, gerar texto, trocar
perfil). Qualquer ação que afete algo fora do seu controle direto — como enviar uma
mensagem para outra pessoa — **nunca** é proativa: passa sempre por confirmação
explícita e, no caso do WhatsApp, por uma whitelist de números (`whatsapp.allowed_numbers`).
Veja a seção [WhatsApp](#whatsapp) nos comandos.

---

## Configuração

Edite `core/config.yaml` (já vem com valores padrão no repositório):

```yaml
# Wake word (deixe vazio para desabilitar e usar push-to-talk)
wake_word:
  enabled: true
  sensitivity: 0.5
  model_path: ""          # Caminho para modelo .onnx customizado (ex: pacoca.onnx)
                          # Para treinar "Paçoca": github.com/dscripka/openWakeWord#training

# IA local
ai:
  provider: ollama        # ollama | groq
  model: qwen3:4b        # qwen3:1.7b em pouca RAM | qwen3:4b | qwen3:8b

# Janela de desktop (texto + microfone + conta Google)
overlay:
  enabled: true            # false = só texto/voz no terminal, sem GUI

# TTS
tts:
  enabled: true
  engine: edge            # edge (online, voz neural) | pyttsx3 (offline) | coqui

# Dashboard web
web:
  password: ""            # deixe vazio para sem autenticação
```

### Groq como fallback (opcional, gratuito)

1. Crie conta gratuita em [console.groq.com](https://console.groq.com) e gere uma API key
2. Defina a variável de ambiente:

```bash
set GROQ_API_KEY=gsk_...      # Windows
export GROQ_API_KEY=gsk_...   # Linux/Mac
```

3. Em `config.yaml`: `ai.provider: groq`

O plano gratuito da Groq oferece 30 requisições/minuto e 6.000 tokens/minuto — mais que suficiente para uso pessoal.

### Memória semântica (opcional, gratuito)

Sem configurar nada, a busca de memórias cai automaticamente para palavra-chave
(comportamento padrão). Para busca por significado de verdade:

```bash
export GEMINI_API_KEY=...   # console.cloud.google.com → AI Studio → API key grátis
```

Ou, sem precisar de chave nova, se você já roda Ollama: `ollama pull nomic-embed-text`.
Detalhes em [configuracao.md](docs/configuracao.md#ai).

### Google Calendar e Drive (opcional)

Configuração manual (ainda não há instalador que automatize este passo):

1. Crie um projeto em [Google Cloud Console](https://console.cloud.google.com)
2. Ative **Calendar API** e **Drive API**
3. Crie credenciais OAuth 2.0 (Aplicativo desktop) e baixe `credentials.json`
4. Coloque em `core/credentials.json`
5. Diga `"autoriza calendário"` — o browser abre para login

O token é salvo em `core/google_token.json` (cobre Calendar + Drive) e renovado automaticamente.

```yaml
calendar:
  credentials_path: core/credentials.json
  token_path: core/google_token.json
  timezone: America/Sao_Paulo

backup:
  google_drive:
    enabled: false
    credentials_path: core/credentials.json
    token_path: core/google_token.json
```

### Obsidian (opcional)

```yaml
obsidian:
  vault_path: C:/Users/seu_usuario/Documents/ObsidianVault/Paçoca
```

### Plugins

Coloque qualquer arquivo `.py` em `plugins/` e ele será carregado automaticamente no próximo boot (ou via `"recarrega plugins"`). Cada plugin deve declarar `NAME`, `VERSION`, `DESCRIPTION` e `ROUTES`. Use `plugins/_template.py` como ponto de partida.

---

## Estrutura do projeto

```
Pacoca/
├── main.py                    # entry point — argparse, boot, bootstrap PyInstaller
├── setup_wizard.py            # assistente de instalação GUI (tkinter, sem deps)
├── setup.bat / setup.sh       # instalação via código-fonte
├── pacoca.spec                # PyInstaller — build do Pacoca.exe (todas as deps bundled)
├── wizard.spec                # PyInstaller — build do Pacoca-Setup.exe
├── build.bat / build.sh       # scripts de build
├── requirements.txt
│
├── core/
│   ├── orchestrator.py        # roteador regex → módulos + plugins + dispatch_chain
│   ├── plugin_loader.py       # escaneia plugins/ e injeta rotas
│   ├── config.py              # carregador YAML com notação de pontos
│   ├── config.yaml            # configuração central
│   ├── profiles.py            # perfis work / casual / focus / meeting / night
│   └── logger.py              # logging rotativo em arquivo
│
├── input/
│   ├── stt.py                 # Whisper + wake word / push-to-talk + calibração
│   ├── hotkeys.py             # atalhos globais
│   └── cli.py                 # interface de terminal
│
├── modules/
│   ├── system_control.py      # apps, volume, brilho, processos
│   ├── transcription.py       # mic + loopback, auto-save
│   ├── summarizer.py          # Ollama + fallback Groq (gratuito)
│   ├── search.py              # roteamento IA local vs DuckDuckGo
│   ├── dev_tools.py           # VS Code, Git, arquivos, testes
│   ├── routines.py            # rotinas YAML com condições
│   ├── productivity.py        # monitoramento, Pomodoro, relatórios
│   ├── security.py            # confirmação de ações críticas
│   ├── backup.py              # backup local + Google Drive
│   ├── calendar_integration.py# Google Calendar — agenda, próximo evento, criar evento
│   ├── reminders.py           # lembretes agendados por voz
│   ├── clipboard_tools.py     # copiar/ler área de transferência por voz
│   ├── screen_reader.py       # OCR de tela via pytesseract
│   ├── meeting_detector.py    # detecta videochamadas via psutil
│   ├── obsidian.py            # exporta notas/transcrições para vault Markdown
│   ├── intent.py             # NLU 3 camadas (TF-IDF, Groq agentivo, Ollama few-shot)
│   ├── tools.py              # registro central de ferramentas do loop agentivo
│   ├── learner.py            # vocabulário, estatísticas e insight proativo
│   ├── semantic_router.py    # camada 2.5 — cache semântico que aprende com o LLM
│   ├── habits.py             # detecta hábitos e sugere rotinas
│   ├── anaphora.py           # resolve seguimento ("de novo", "fecha ele", "e amanhã?")
│   ├── trust.py              # confiança aprendida para reduzir confirmações
│   └── web_server.py          # inicia o servidor do dashboard
│
├── output/
│   ├── tts.py                 # edge-tts (padrão) com fallback pyttsx3/Coqui
│   ├── overlay.py             # janela de desktop PyQt6 (texto/mic/conta Google), thread-safe
│   └── notifier.py            # notificações desktop
│
├── storage/
│   ├── db.py                  # SQLite — histórico e sessões
│   ├── file_store.py          # transcrições e resumos em Markdown
│   └── context.py             # memória contextual de sessão (ring buffer)
│
├── web/
│   ├── __init__.py
│   └── app.py                 # FastAPI + htmx + WebSocket — dashboard local
│
├── plugins/
│   ├── notes.py               # anotações rápidas (plugin incluso)
│   └── _template.py           # template para novos plugins
│
├── hooks/                     # runtime hooks do PyInstaller
│
└── tests/                     # 304 testes (pytest)
    ├── test_config.py
    ├── test_db.py
    ├── test_orchestrator.py
    ├── test_dispatch_chain.py
    ├── test_reminders.py
    ├── test_context.py
    ├── test_providers.py      # circuit breaker, cache TTL, retry
    ├── test_telemetry.py
    └── test_web_endpoints.py  # auth, CSRF, rate limit, sessão do dashboard
```

---

## Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper (Whisper base) | Local / offline |
| Wake word | openWakeWord (sem API key) | Local / offline |
| LLM | Ollama (llama3 / mistral / phi3) | Local / offline |
| LLM cloud | Groq API (llama3, free tier) | Opcional / gratuito |
| Embeddings (memória semântica) | Gemini API (free tier) ou Ollama local (`nomic-embed-text`) | Opcional / gratuito |
| TTS | edge-tts (padrão, voz neural) com fallback para pyttsx3 | Gratuito / offline opcional |
| Busca web | duckduckgo-search | Gratuito |
| Janela de desktop | PyQt6 | Open-source |
| Monitoramento | psutil | Open-source |
| Banco de dados | SQLite | Open-source |
| Backup nuvem | Google Drive API | Gratuito |
| Google Calendar | Google Calendar API (OAuth 2.0) | Gratuito |
| Dashboard web | FastAPI + htmx + uvicorn + WebSocket | Open-source |
| Config | PyYAML | Open-source |
| Empacotamento | PyInstaller | Open-source |

---

## Testes

```bash
python -m pytest tests/ -v
```

349 testes (8 skipped — exigem rede/credenciais reais) cobrindo: config, orchestrator
(roteamento), banco de dados, STT, dev tools, dispatch_chain, lembretes, memória
contextual, providers (circuit breaker, cache, retry), telemetria, endpoints do
dashboard web (autenticação, CSRF, rate limit, sessão), os agendadores autônomos
(rotinas agendadas, briefing diário, pausa proativa, sumário pós-reunião, insight
de aprendizado), o envio de WhatsApp (whitelist, confirmação, ToolRegistry) e a
camada de inteligência adaptativa (cache semântico + guard de slot, detecção de
hábitos, anáfora/seguimento, confiança aprendida em confirmações).

CI automático via GitHub Actions em cada push para `main`/`dev`, em matriz
Windows + Linux.

---

## Roadmap

### v0.1 — Concluído
- [x] Boot completo com logger, db e produtividade
- [x] Modo texto e modo voz (push-to-talk)
- [x] Overlay flutuante com estado e histórico
- [x] Transcrição mic + loopback + auto-save
- [x] Dev tools: git por voz, abrir arquivo, explicar código
- [x] Pomodoro, relatório diário, rotinas com condições
- [x] CI/CD com GitHub Actions

### v0.2 — Concluído
- [x] Calibração automática de ruído para o microfone
- [x] Integração com Google Calendar
- [x] Perfis dinâmicos por voz (work / casual / focus / meeting / night)
- [x] Plugin system — carregamento dinâmico e hot-reload por voz
- [x] Speaker diarization (`pyannote.audio`) — opcional, requer HF_TOKEN

### v0.3 — Concluído
- [x] Memória contextual — histórico da sessão injetado no prompt do LLM
- [x] Lembretes por voz — horário absoluto e relativo
- [x] Clipboard por voz
- [x] OCR de tela via pytesseract + Pillow
- [x] Troca de idioma STT por voz
- [x] Sumário de reunião estruturado + sumário de sessão

### v0.4 — Concluído
- [x] Dashboard web local (FastAPI + htmx) em localhost:7755
- [x] Exportação para Obsidian
- [x] Comandos encadeados naturais
- [x] Modo reunião automático (detecta Zoom/Teams/Slack via psutil)
- [x] TTS profile-aware
- [x] Flag `--web`

### v0.5 — Concluído
- [x] 73 testes — dispatch_chain, reminders e context
- [x] Dashboard WebSocket — resposta instantânea + push de eventos em tempo real
- [x] Editor visual de rotinas no dashboard (htmx CRUD)
- [x] Autenticação no dashboard — cookie + login (`web.password`)
- [x] **Pacoca.exe standalone** — todas as deps Python bundled via PyInstaller; zero pip install para o usuário final
- [x] **Setup wizard GUI** (`Pacoca-Setup.exe`) — instala Ollama, faz login Google, cria atalho; roda em qualquer PC Windows sem Python instalado
- [x] Token Google unificado (`google_token.json`) — cobre Calendar + Drive em um único OAuth

### v0.6 — Concluído
- [x] Substituição do Anthropic por **Groq** como fallback cloud (free tier, llama3)
- [x] `credentials.json` OAuth embutido diretamente no `Pacoca-Setup.exe` via PyInstaller
- [x] OAuth Google simplificado no wizard — fluxo unificado sem etapas manuais
- [x] Wizard baixa `Pacoca.exe` automaticamente se não encontrado na pasta
- [x] openWakeWord substituindo pvporcupine (sem API key, totalmente open-source)

### Não lançado (atual)
- [x] Arquitetura de providers centralizada (`core/providers.py`) — circuit breaker,
      retry exponencial, cache TTL, pool de conexões HTTP
- [x] Telemetria de comandos (`core/telemetry.py`) — exposta em `/metrics`
- [x] Síntese de voz neural — `edge-tts` como motor padrão (fallback automático para pyttsx3)
- [x] Testes para `web/app.py` (auth, CSRF, rate limit, sessão) e `core/providers.py`
- [x] Sessão do dashboard com cookie assinado (HMAC) em vez de hash estático da senha
- [x] CI em matriz Windows + Linux
- [x] **Memória semântica** (`core/embeddings.py`) — busca por significado, não só
      palavra-chave, via Gemini (free tier) ou Ollama local (`nomic-embed-text`)
- [x] Loop agentivo mais confiável — retry automático para falhas de formatação do
      Groq, e nunca afirma sucesso quando uma ferramenta falhou de verdade
- [x] **CRUD completo de calendário** no loop agentivo — criar, ler, editar e apagar
      eventos, incluindo convidados por e-mail
- [x] **Janela de desktop** (texto, microfone, conta Google) — `overlay.enabled: true`

### v0.7 — Concluído (proatividade / autonomia)
- [x] **Rotinas com agendamento automático** — `schedule: {time, days}` em
      `routines:` dispara a rotina sozinha, sem comando do usuário
- [x] **Briefing diário proativo** (`modules/briefing.py`) — clima + agenda +
      lembretes + uso do dia anterior, gerado e notificado sozinho no horário
      configurado (`briefing.time`)
- [x] **Sugestão proativa de pausa** — avisa quando passa muito tempo sem
      descanso (`productivity.break_after_min`); "tomei uma pausa" reseta
- [x] **Sumário automático pós-reunião** — ao detectar o fim da chamada, gera
      e salva o sumário estruturado sozinho (`meeting_detector.auto_summarize`)
- [x] **Insight de aprendizado periódico** (`modules/learner.py`) — analisa o
      histórico e notifica sozinho, sem precisar do comando "o que você aprendeu"
- [x] **Mensagens WhatsApp** (`modules/whatsapp.py`, via `pywhatkit`) — composição
      natural pelo LLM, sempre com confirmação explícita + whitelist de números
      (`whatsapp.allowed_numbers`) como segunda barreira de segurança
- [x] 29 novos testes cobrindo os itens acima (329 no total)

### v0.8 — Concluído (inteligência adaptativa)
- [x] **Roteamento semântico que aprende** (`modules/semantic_router.py`) — camada
      2.5: memoriza resoluções do LLM e serve paráfrases futuras localmente, com
      guard anti-erro de slot
- [x] **Detector de hábitos** (`modules/habits.py`) — observa padrões recorrentes
      e sugere virar rotina, sozinho ou sob demanda ("sugestões")
- [x] **Resolução de anáfora/seguimento** (`modules/anaphora.py`) — "de novo",
      "fecha ele", "e amanhã?", "e em Recife?"
- [x] **Confiança aprendida em confirmações** (`modules/trust.py`) — deixa de
      confirmar ações de risco médio aprovadas N vezes; risco alto sempre confirma
- [x] 20 novos testes cobrindo os itens acima (349 no total)

### Próximo
- [ ] Streaming de resposta do LLM — tokens em tempo real no dashboard/janela de desktop
- [ ] Treinar modelo de wake word "Paçoca" customizado (hoje usa `hey_jarvis`)
- [ ] Validar `pacoca.spec`/`wizard.spec` gerando um executável funcional e
      publicar a primeira release no GitHub (`pacoca.spec`/`wizard.spec` existem
      no repositório, mas **ainda não há nenhuma release publicada**)

---

## Contribuição

1. Fork o repositório
2. Crie um módulo em `modules/` seguindo o padrão: funções públicas retornam `str`, use lazy imports
3. Registre as rotas em `core/orchestrator.py`
4. Adicione testes em `tests/`
5. Abra um Pull Request para `dev`

---

## Licença

MIT License — veja [LICENSE](LICENSE)

---

## Autor

Desenvolvido por [Athy (AthirsonLamonato)](https://github.com/AthirsonLamonato)

### Capacidades ampliadas do agente de navegador

Além das operações básicas, o navegador local agora suporta abas, histórico, espera por conteúdo dinâmico, teclas, seleção de opções, listagem de links e downloads controlados. Downloads exigem confirmação e são salvos somente em `data/downloads`; screenshots são limitados ao diretório `data/`.

Os planos supervisionados são persistidos em `data/task-plans.json`, sobrevivem a reinícios e ocultam valores de credenciais na resposta do dashboard. A página de planos mostra as etapas antes da aprovação e os resultados detalhados depois da execução. A suíte de integração cobre autenticação, CSRF, criação, rejeição e consulta de planos.

### IA local sem custo

O Paçoca usa Ollama como provedor padrão para não depender de API paga. Para uma instalação equilibrada, execute `ollama pull qwen3:4b` e `ollama pull nomic-embed-text`. Em computadores com pouca RAM, use `qwen3:1.7b`. O catálogo e a recomendação automática ficam em `core/ai_catalog.py`; o dashboard expõe `GET /api/ai/models` e `GET /api/ai/diagnostics` para mostrar a memória detectada, o modelo recomendado, a conectividade do Ollama e os modelos instalados sem expor chaves.


## Segurança operacional

O executor de planos possui cancelamento cooperativo e timeout total. No dashboard, planos pendentes podem ser cancelados e planos em execução podem ser interrompidos entre etapas. Também é possível configurar perfis com risco máximo e listas de ferramentas permitidas ou bloqueadas em `security.profile_policies` no `core/config.yaml`.

O perfil `work` mantém compatibilidade com todas as ferramentas, sempre respeitando confirmações. Perfis como `focus`, `meeting` e `night` podem restringir ações de alto risco. Por exemplo:

```yaml
security:
  profile_policies:
    focus:
      max_risk: medium
      allowed_tools: []
      denied_tools:
        - git_operation
        - close_application
        - send_whatsapp_message
```

Uma lista vazia em `allowed_tools` significa que todas as ferramentas abaixo do risco máximo são permitidas. A política é aplicada no registro central de ferramentas, antes da execução.


### Backup e restauração local

O backup automático inclui transcrições, resumos, a base de conhecimento e planos persistentes. Cada cópia contém um `manifest.json` com os itens incluídos e excluídos. Perfil do navegador, downloads, credenciais e tokens nunca entram no backup automático. A quantidade de cópias mantidas é controlada por `backup.keep`.

A restauração deve ser feita somente com um caminho criado pelo próprio Paçoca dentro de `backup.local_dir`; caminhos externos são rejeitados. A função restaura apenas diretórios e arquivos reconhecidos (`transcriptions`, `summaries`, `kb` e `task-plans.json`).
