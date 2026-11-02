# Validação da nova Paçoca

Data: 01/11/2026. Aplicação recriada em `src/pacoca/`, branch `feat/pacoca-local-desktop`.

## Base e distribuição

A aplicação nova não importa o código legado. Usa FastAPI local, janela PySide6/QtWebEngine, SQLite, llama.cpp b12032, Qwen3 8B Q4_K_M, Whisper small e Piper pt-BR. O motor local tenta CUDA em NVIDIA compatível, Vulkan e, por último, CPU. O instalador contém bibliotecas, voz e transcrição e provisiona o modelo de conversa por download HTTPS com revisão e SHA-256 fixados. A instalação inicial precisa de internet; a IA instalada funciona localmente.

Uma decisão semântica local seleciona a ferramenta inicial. Seus argumentos são gerados com JSON Schema e validados com Pydantic antes da autorização/execução. Os resultados observados retornam ao modelo para responder ou decidir as próximas etapas. Esse caminho foi reforçado após testes reais detectarem respostas sem uso das ferramentas; texto de conversa não é aceito como execução de uma ação selecionada.

## Testes automatizados

26 testes passaram com:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests_next -p pytest_asyncio.plugin -q
```

Cobertura dirigida: persistência, memória editável, limites de pastas, revogação de acesso, índice e exclusão de credenciais conhecidas, contratos de ferramentas, bloqueio de escrita sem aprovação, cancelamento de autorização, recuperação sem repetição automática, marcação de áudio interrompido, histórico de etapas, rejeição de texto não fundamentado para uma ação, autenticação local, proteção de origem/Host, restrições de Alexa e Job Object para encerrar o processo auxiliar.

Também passaram a compilação Python e a análise de sintaxe dos arquivos JavaScript. A integração contínua da base nova fica em `.github/workflows/desktop.yml`; sua execução remota ainda não foi observada nesta entrega local.

## Testes reais com modelo e ferramentas

O script `scripts/check_tools.py` executou 12 cenários com o modelo local real, em dados de teste isolados:

| Cenário | Evidência |
| --- | --- |
| Data e hora | `current_time` consultou o relógio local. |
| Sistema e RAM | `computer_info` consultou Windows e aproximadamente 31,9 GB de RAM. |
| Aplicativos | `list_applications` encontrou Bloco de notas. |
| Janelas | `list_windows` consultou janelas reais e respondeu a contagem. |
| Volume | `volume` consultou o valor real sem alteração solicitada. |
| Escrita | `write_file`, após autorização de teste, salvou e verificou o conteúdo no Workspace isolado. |
| Leitura | `files` leu o orçamento de 321 reais no arquivo criado. |
| Guardar memória | `remember`, após autorização de teste, persistiu uma preferência sintética. |
| Consultar memória | `list_memories` leu a preferência salva. |
| Criar lembrete | `create_reminder` persistiu uma data futura no ambiente isolado. |
| Consultar lembrete | `list_reminders` retornou o lembrete criado. |
| Navegador | `browser` abriu example.com e observou o título Example Domain. |

Resultado: **12 de 12 cenários com a ferramenta esperada e retorno sem erro**, repetidos também no executável empacotado. Isso mede esse conjunto explícito, não uma taxa geral de acerto em qualquer tarefa do computador. Os scripts de teste só aprovam ações sobre seus dados descartáveis e o domínio de demonstração. Na repetição empacotada, as etapas variaram aproximadamente de 2,25 a 41,12 s; memória levou 41,12 s e a primeira abertura do navegador 37,30 s. Esses casos impedem prometer uma latência uniforme de poucos segundos para qualquer ferramenta.

Também passaram três fluxos reais de várias etapas em `scripts/check_multistep.py`: consultar hora e RAM no mesmo pedido; criar dois arquivos distintos com autorização e verificação; ler ambos e apresentar o conteúdo de cada um. Os fluxos chamaram duas ferramentas/etapas cada e levaram aproximadamente 4,06 a 4,47 s na execução observada.

## Conversa, interface e áudio

`scripts/check_app.py` verificou inferência real, continuidade de contexto entre turnos, memória pela interface e telas responsivas. Houve inspeção visual das capturas e da janela nativa Windows via Computer Use. O navegador de testes não registrou erros de JavaScript.

`scripts/check_voice.py` verificou geração de voz local, envio de áudio progressivo, captura por um microfone simulado do Chromium, transcrição real com Whisper, resposta e interrupção. O áudio de entrada era sintético: **nenhum microfone humano foi gravado**. A voz gerada dizia uma apresentação da Paçoca e a transcrição reconheceu o conteúdo em português.

No executável final com modelos aquecidos: primeiro texto em aproximadamente 0,81 s e primeiro áudio em 1,03 s. A primeira inicialização da síntese levou mais tempo (primeiro áudio em aproximadamente 6,34 s em um teste anterior). A aplicação pré-carrega os modelos de áudio para reduzir esse custo. Esses números são amostras, não percentis nem garantias para outros equipamentos.

Máquina usada: Windows 11, Ryzen 7 5700X3D, aproximadamente 32 GB de RAM, RTX 4060 Ti de 8 GB. No teste com CUDA, os quatro turnos de conversa/contexto levaram aproximadamente 2,25 a 3,5 s para a resposta completa.

## Executável e instalador 1.0.0: registro inicial

O PyInstaller gerou o executável, e `scripts/verify_bundle.py` confirmou que todos os módulos da aplicação e os arquivos de interface empacotados correspondem ao código atual. Foi corrigida uma falha de segunda instância: no Windows, até a leitura do byte já bloqueado causava erro. A segunda abertura agora ativa a primeira e encerra, e esse comportamento passou no executável real.

`scripts/check_distribution.py` executou o binário com PATH limitado aos diretórios do Windows, sem PYTHONPATH/PYTHONHOME/venv. A consulta de horário com ferramenta real, resposta, síntese WAV e segunda instância passaram tanto em CUDA como em CPU. Os testes de conversa/contexto, cinco capturas responsivas, áudio sintético e os 12 cenários de ferramentas também passaram sobre o executável.

A tentativa de incorporar o modelo 8B inteiro foi rejeitada pelo compilador de instalação por exceder 4.200.000.000 bytes em um único Setup.exe. A distribuição preserva um único instalador: os componentes locais ficam no pacote e o próprio instalador baixa o modelo oficial fixado, com verificação de hash e reaproveitamento se a cópia já instalada estiver correta. Nenhum outro aplicativo nem conta de IA é necessário.

`scripts/check_installer.py` instalou a distribuição em `.test-data/installed-app`: saída 0, aproximadamente 250,38 s, download real observado e nenhuma reinicialização do Windows. O SHA-256 do modelo instalado corresponde ao recurso oficial validado. Código-fonte e licenças também foram encontrados na instalação.

- Arquivo: `release/Pacoca-Setup.exe`.
- Tamanho: **1.848.614.989 bytes** (aproximadamente 1,85 GB).
- SHA-256: `76c274812a3cbd3d2bc84a0ded6f89d4e3ba244569534ee846c6291dcb74d036`.
- A instalação inicial exige internet para o modelo de aproximadamente 5 GB; o funcionamento da IA instalada é local.

A inspeção visual final da janela instalada foi interrompida pelo usuário com a tecla física Esc no Computer Use. A automação de interface foi encerrada, e esse último teste não é considerado aprovado. Os testes de executável, voz, ferramentas e interface descritos acima pertencem ao binário em `dist/Pacoca`, enquanto o teste do instalador comprova instalação, download e integridade. A pasta de instalação isolada foi preservada.

## Correção 1.0.1: carregamento da interface nativa

A imagem de erro enviada pelo usuário revelou uma falha real da distribuição 1.0.0: `DLL load failed while importing QtCore`. A análise do arquivo `Analysis-00.toc` mostrou que o empacotador havia resolvido `icuuc.dll` pelo PATH de uma ferramenta Poppler do ambiente de desenvolvimento. Essa ICU exporta símbolos versionados, enquanto o Qt deste pacote importa a API C sem sufixos fornecida pelo Windows. Os testes anteriores sem janela não detectavam essa incompatibilidade.

O build agora limita o PATH aos diretórios do Python usado para compilar e do Windows, exclui essas DLLs privadas de ICU do pacote e rejeita sua presença na verificação da distribuição. A atualização remove os dois arquivos incompatíveis que a 1.0.0 instalou. O modelo e os dados pessoais são preservados.

O teste nativo tornou-se uma etapa obrigatória antes de empacotar: a aplicação registra a renderização real da página por QtWebEngine, e o script espera essa confirmação em vez de aceitar apenas um servidor HTTP ativo. No primeiro teste da 1.0.1, a janela renderizou com Qt 6.12.0, CUDA carregou, a ferramenta `current_time` foi executada, a síntese gerou WAV e a segunda instância ativou a primeira. Os 26 testes automatizados continuam passando.

A atualização sobre a instalação 1.0.0 terminou com saída 0 em aproximadamente 155,88 s. Os arquivos incompatíveis foram removidos, o hash do modelo permaneceu correto e **não houve novo download do modelo**. A aplicação instalada, sem acesso aos caminhos de desenvolvimento e sem override dos recursos, passou pelo teste nativo completo: renderização, CUDA, ferramenta real, síntese de WAV e segunda instância.

O mapa de bibliotecas do processo instalado confirmou `icuuc.dll` e `icu.dll` de `C:\Windows\System32`, com `Qt6Core.dll` da instalação. Em seguida, a aplicação foi iniciada normalmente com o perfil real do usuário: versão 1.0.1, janela renderizada e motor CUDA pronto, sem inserir conversas de teste nesse perfil. Evidências locais: `.test-data/evidence/installation.json`, `installed-fix.json`, `native-libraries.json` e `user-launch.json`.

A inspeção de acessibilidade pelo Computer Use encontrou a janela da Paçoca e sua tela de apresentação, com o campo “Como posso chamar você?” e o botão “Vamos começar”. A captura de imagem desse recurso retornou outra superfície e não foi usada como evidência visual de layout. Nenhum campo do perfil real foi preenchido, e nenhum microfone humano foi capturado.

**Distribuição atual 1.0.1:**

- Arquivo: `release/Pacoca-Setup.exe`.
- Tamanho: **1.834.136.292 bytes** (aproximadamente 1,83 GB).
- SHA-256: `1e169586066443d21186ce741abd876982ffa02356ecefb5e16feb4068745d03`.
- O modelo 8B e o funcionamento local foram mantidos. O instalador reaproveita o modelo já válido e preserva conversas e preferências.

## Limites da evidência

- Ainda é necessário avaliar microfone, ruído, interrupção por fala e alto-falantes reais com o usuário. O teste sintético não comprova qualidade acústica no ambiente dele.
- Os testes de UI Automation não equivalem a homologar todos os aplicativos do Windows. UAC e tela bloqueada não são contornados.
- Alexa tem adaptador, modelo de interação e testes de rejeição/deduplicação. O Echo real depende de skill, conta e endpoint HTTPS do usuário e não foi homologado nesta execução.
- A instalação em um Windows limpo, sem ferramentas de desenvolvimento previamente presentes, precisa de um ambiente próprio de homologação. Não foi reutilizada nenhuma VM de outros projetos.
- A ativação por palavra-chave e a restauração automática do JSON exportado não estão habilitadas nesta distribuição.

O código, os testes, os modelos fixados e as instruções de build permitem repetir a validação sem APIs de IA pagas.

## Versão 1.1.1 — leveza, atualizações e comandos (02/11/2026)

O modo padrão passou a ser Qwen3 1.7B Q4_K_M, quantizado por Unsloth e fixado por revisão/SHA-256. O 8B existente é preservado, mas sua carga depende de escolha manual; o instalador oferece seu download como opcional. A inicialização não carrega o modelo nem os motores de áudio. Linguagem usa CPU com dois threads e prioridade reduzida; áudio usa um processo separado de um thread, sem espera ativa do ONNX Runtime. Há limites de CPU por Windows Job e liberação dos processos após inatividade. A proteção de jogos impede o 8B durante jogos conhecidos, e o fluxo de abertura de CS2/Valorant libera o modelo antes de iniciar o aplicativo.

Evidências desta revisão:

- **80 testes automatizados passaram**, cobrindo a base, migração para o modo leve, modelo ausente, proteção de jogos, assinatura e escopo dos pacotes, primeira busca após inicialização recente do Windows, bloqueios de atualização, comandos explícitos, ambiguidades, isolamento do player do navegador, seleção de dispositivo em cenário controlado e fluxo observado do mata-mata. Um clique observado é recusado se a janela mudar de posição ou tamanho ou perder o foco.
- O teste nativo isolado da distribuição 1.1 mediu **372 MB de RSS no conjunto de processos da janela e 0,07% da CPU do computador em repouso**. IA e áudio permaneciam descarregados. QtWebEngine 6.12 renderizou a página; OCR sobre uma imagem sintética, projeções de mídia do Windows, conversa em CPU, síntese WAV e segunda instância passaram sem PATH de desenvolvimento. São amostras de três segundos nesta máquina, não percentis nem garantias universais.
- `check_resources.py` mediu **3.444 MB de RSS** com linguagem, transcrição e síntese carregadas simultaneamente; pico de CPU observado de **14% do computador** durante os turnos. O servidor voltou a aproximadamente **82 MB** após liberação dos motores. Esse teste era sem janela e rodou enquanto o projeto era compilado. As respostas textuais curtas levaram aproximadamente 7,6–16,4 s; uma resposta com síntese levou 13,4 s. Em uma medição anterior sem transcrição residente, o conjunto atingiu aproximadamente 2.595 MB; esse número não representa toda a sessão de voz.
- Os **12 cenários com ferramentas reais passaram no modo leve em CPU**: horário, sistema, aplicativos instalados, consulta de janelas, consulta de volume, escrita/leitura em Workspace de teste, memória, consulta de memórias, criação/consulta de lembretes e navegação em example.com. As etapas com modelo semântico e ferramentas levaram aproximadamente 29–71 s nesta execução; comandos diretos usam adaptadores sem passar pelo modelo. Não houve captura de microfone humano.
- A interface passou por teste de navegador headless em 1440 e 640 pixels, sem erros de página nem rolagem horizontal; preferências foram salvas e relidas. A instrumentação do navegador de teste permitiu introspecção sob CSP, sem alterar a política da aplicação.

O auxiliar real de atualização passou por testes com executáveis descartáveis: instalação, assinatura inválida e restauração após executável inválido. A troca **entre distribuições Qt reais 1.1.0 e 1.1.1** também passou em aproximadamente **51,6 s**, por feed assinado em localhost: download e instalação automáticos, backup SQLite, memória preservada, modelo sem alteração, novo PID e janela realmente renderizada. A primeira consulta do protótipo QA 1.1.0 foi iniciada pela API porque ele precedia a correção de primeira busca; depois da troca, a 1.1.1 foi reiniciada e comprovou a busca automática com Windows ligado havia menos de seis horas. A proteção contra instalação durante jogos e sessão de voz foi testada com estados controlados. A restauração por falha foi testada com executável descartável; não foi induzida uma falha de DLL na janela final do usuário.

A integração Spotify usa acessibilidade do aplicativo, OCR local do seletor Connect e sessões de mídia nativas do Windows, sem Web API, client secret ou endpoints privados. Na inspeção do Spotify instalado, a Echo apareceu no seletor. O usuário interrompeu Computer Use pela tecla física Esc; nenhuma outra interação com seus aplicativos foi feita depois disso. **Reprodução física no PC/Echo/celular e uma busca real de partida no CS2 não foram homologadas nesta revisão.** As verificações dos fluxos e ambiguidades foram realizadas com cenários controlados; menus alterados, autenticação, foco, dispositivos ausentes ou resultados ambíguos retornam estado não verificado, em vez de anunciar sucesso.

O teste em localhost não comprova a disponibilidade do canal público. A assinatura e os artefatos ficam preparados para uma release no GitHub; sua publicação e a verificação dos downloads públicos são etapas separadas. A versão 1.0.1 precisa receber este instalador uma vez para passar a dispor do atualizador novo.

Evidências locais (não publicadas): `.test-data/evidence/resources.json`, `tools-test.json`, `light-browser.json`, `baseline-native.json`, `build-native.json`, `update-transactions.json` e `real-update.json`.

### Instalação e publicação concluídas

O instalador final 1.1.1 passou pela instalação isolada com download real do modelo leve e hash correto, em aproximadamente 174 s. O aplicativo instalado passou por renderização Qt, conversa em CPU, áudio, OCR, mídia nativa, catálogo com 145 aplicativos e segunda instância, sem caminhos de desenvolvimento ou recursos externos à instalação.

A instalação 1.0.1 do usuário foi atualizada depois de backup do aplicativo e do banco. Conversas, mensagens e memórias mantiveram suas contagens; os modelos anteriores não foram alterados. A 1.1.1 iniciou minimizada no modo leve, sem carregar linguagem ou áudio, com aproximadamente 358 MB no conjunto de processos. Não foram inseridas conversas de teste no perfil real.

A release pública [v1.1.1](https://github.com/AthirsonLamonato/Pacoca/releases/tag/v1.1.1) foi publicada como Latest após aprovação do usuário. Os sete arquivos enviados tiveram tamanho e SHA-256 comparados com os digests do GitHub. O manifesto e os checksums foram baixados pelo endereço público; os pacotes responderam pelo canal público e a assinatura foi validada. A aplicação instalada consultou esse mesmo canal e retornou `current`, versão 1.1.1 e atualizações automáticas habilitadas. A CI Desktop e os testes legados em Windows/Linux passaram. A CI antiga recebeu dados de fuso horário e seus cenários de X11/Wayland passaram a simular Linux explicitamente; o código legado da aplicação foi preservado.

Instalador: 1.834.552.758 bytes; SHA-256 `1bfb3976a38bc6e1267a2f0d299369cc21a125c10feef08264daeb4bdf5efaff`. Atualização normal da aplicação: aproximadamente 20 MB; runtime completo para mudanças de dependências: aproximadamente 429 MB. Modelos ficam fora desses pacotes.

## Ativação local por nome — 1.2.0

O detector PocketSphinx 5.0.4 usa somente seu modelo acústico pequeno e um dicionário de pronúncias para “Paçoca”. O modelo é fixado por SHA-256 em `packaging/wake-model.lock.json` e sua identidade participa do runtime de atualização. O processo é separado de Whisper/Piper, tem prioridade reduzida, recebe limite de CPU de 5% no Windows e termina ao pausar a escuta. Um único fluxo WebAudio fornece PCM de 16 kHz ao servidor em loopback autenticado. O áudio de espera não é salvo; o buffer circular de quatro segundos preserva o nome e o início do pedido.

Os 96 testes locais passaram, incluindo doze amostras sintéticas positivas/negativas reais do detector, isolamento e liberação do processo, autenticação, limites dos blocos, pausa e bloqueio de atualização durante ativação (a espera não bloqueia atualizações). Uma sondagem adicional com Piper a 0,8× e 1,2× reconheceu seis chamadas e rejeitou quatro frases com pessoa/pipoca. Isso não equivale a um teste com vozes humanas diferentes.

A interface em Chromium passou por microfone fictício com áudio local gerado: chamada e pedido na mesma frase, transcrição do pedido, resposta local, retorno automático à espera e pausa persistente após nova consulta de status; sem erros JavaScript. Nesse teste sem Qt, a espera usou aproximadamente 106 MB no conjunto de processos do servidor, 28 MB no detector e 0,17% da CPU total, sem modelos de linguagem/transcrição carregados. A resposta completa com carregamento frio do modelo leve levou cerca de dois minutos; a espera de palavra-chave não elimina a latência dos modelos de conversa. A qualidade factual da resposta não foi homologada por esse teste de transporte de voz.

Também passou a chamada separada: “Paçoca”, pausa e “Pare de ouvir”, com confirmação pela transcrição e fechamento da captura por voz, em aproximadamente 33,5 s no cenário sintético completo (incluindo 14 s iniciais de silêncio). O nome fica em memória até chegar o pedido, para não perder a segunda frase enquanto Whisper carrega. A transcrição acrescentou “ele” ao comando sintético; o comando de pausa aceita esse complemento porque começa com uma instrução explícita para parar de ouvir.

Evidências de desenvolvimento: `.test-data/wake-browser/result.json` e `.test-data/wake-browser/paused.png`. Microfone humano não foi capturado. Reconhecimento da voz do usuário, sotaques, ruído real e reprodução pelos alto-falantes precisam de validação física; a sensibilidade fica disponível nas configurações.

O executável empacotado também passou pelo microfone sintético na janela Qt realmente minimizada: chamada separada do pedido e pausa do microfone por voz, em aproximadamente 41,2 s incluindo silêncio inicial. A espera mediu aproximadamente 526 MB no conjunto de processos e 0,99% da CPU total, com cerca de 50 MB no detector, sem Whisper ou modelo de conversa carregados. Esse cenário inclui microfone fictício e depuração local da janela para observar seu estado. O carregamento nativo revelou que PocketSphinx consulta seu namespace de modelos ao construir a configuração; o pacote inclui o aviso original em `pocketsphinx/model/README` para disponibilizar esse namespace, além dos arquivos acústicos próprios em `wakeword/en-us`. Esse recurso participa da identidade e da verificação do runtime.

A troca de microfone durante uma sessão manual e uma consulta de status enquanto a captura iniciava passaram na interface de desenvolvimento, sem capturas duplicadas ou erros JavaScript. A verificação da distribuição confirmou que bytecode, interface, dicionário, runtime e arquivos acústicos correspondem ao código atual; o gate nativo confirmou renderização Qt, conversa em CPU, áudio, OCR, mídia e segunda instância.

### Distribuição e atualização 1.2.0

O instalador de 1.839.933.614 bytes passou pela instalação isolada em 138,47 s, reutilizando o modelo leve existente sem download. SHA-256: `fb87964d2d289e79f76227a5115cd77fed967dd18208d6937d52575e1610679b`. O aplicativo dessa instalação passou pela chamada separada e pausa por voz na janela minimizada, sem PYTHONPATH, VIRTUAL_ENV, ferramentas de desenvolvimento no PATH ou sobrescrita do diretório de modelos. Os recursos vieram da própria instalação. Foram aproximadamente 540 MB no conjunto de processos, 51 MB no detector e 1% da CPU total na espera; sem carregamento de Whisper ou linguagem. O cenário completo sintético levou 42,5 s, incluindo silêncio inicial.

A atualização entre cópias reais 1.1.1 e 1.2.0 passou pelo feed local assinado em 171,31 s, usando o runtime completo novo: banco com backup, memória preservada, modelo intocado, novo PID, Qt 6.12.0 renderizado e busca automática do canal após reinício frio.

A release pública [v1.2.0](https://github.com/AthirsonLamonato/Pacoca/releases/tag/v1.2.0) foi liberada após a CI Desktop e os testes legados de Windows/Linux passarem no commit `f2d5404`. Os seis artefatos de distribuição enviados tiveram tamanho e SHA-256 comparados aos digests do GitHub. O manifesto público Latest teve assinatura e versão 1.2.0 verificadas; o arquivo de checksums baixado coincide byte a byte com o local. O pacote normal da aplicação tem 20.032.956 bytes e o runtime completo tem 434.688.553 bytes; a 1.1.1 recebe o runtime novo para incluir o detector. Os modelos de conversa ficam fora da atualização.

A instalação de uso do usuário recebeu a 1.2.0 pelo próprio canal público assinado, em aproximadamente 210,3 s. O recibo confirmou instalação e nova janela Qt renderizada; a conversa existente e as contagens de memórias foram preservadas. A preferência de escuta por nome foi ativada conforme solicitado, e o aplicativo confirmou processo detector vivo no microfone configurado, sem Whisper ou modelo de linguagem carregados. O atualizador retornou `current`. A abertura real do microfone foi confirmada; não foram gravadas amostras humanas para homologar o reconhecimento da voz do usuário. As provas de transcrição e comandos desta entrega continuam sendo sintéticas. Os metadados da instalação de uso foram preservados após o teste isolado do instalador.

O roteiro `scripts/check_wake.py` inclui chamada e pedido juntos, chamada separada com pausa por voz, troca de microfone e consulta de status durante a abertura da captura. Na versão final, a prova nativa usa o arquivo de renderização do próprio aplicativo e remove caminhos de desenvolvimento; não precisa abrir depuração remota da janela.
