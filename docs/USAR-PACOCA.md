# Sua Paçoca

A Paçoca é uma assistente pessoal de Windows com conversa, voz e memória locais. Seu único instalador inclui o motor de execução, reconhecimento de fala e síntese de voz, e baixa automaticamente o modelo de linguagem para o PC. O aplicativo novo fica em `src/pacoca/` e não importa módulos do projeto anterior.

## Instalar e começar

1. Com internet disponível, execute `Pacoca-Setup.exe` e escolha a pasta de instalação. O próprio instalador baixa aproximadamente 1,1 GB do modelo leve gratuito e verifica seu SHA-256. Reserve aproximadamente 12 GB livres (20 GB com o 8B opcional) durante o preparo. Não há outro instalador nem conta de IA.
2. Abra **Paçoca** pelo atalho. No primeiro acesso, informe como prefere ser chamado.
3. A janela já está pronta: os modelos só carregam quando forem necessários.
4. Digite uma mensagem ou clique em **Vamos conversar**.
5. Em **Configurações**, selecione o microfone e a saída de áudio. Use **Ouvir minha voz** para conferir a reprodução.

O aplicativo não exige Python, Ollama, LM Studio, conta de IA ou chave de API. Depois de instalado, conversa, transcrição, voz e memória não precisam de internet. O primeiro carregamento e a primeira transcrição podem demorar mais. O desempenho em CPU é diferente do desempenho em GPU.

## Conversar por voz

Sem a chamada pelo nome ativada, o microfone abre durante a sessão iniciada por você. Com a chamada ativada, ele também permanece aberto enquanto espera “Paçoca”. A barra **Estou ouvindo você** indica a sessão de conversa. Faça uma pequena pausa ao terminar cada fala; a Paçoca transcreve e responde. Você pode começar outra fala para interromper o áudio anterior. **Encerrar conversa por voz** fecha o microfone no modo manual. Com a chamada ativada, use **Voltar à espera** para aguardar o nome ou **Pausar microfone** para fechar a captura. Você também pode dizer “Pare de ouvir”.

O botão **■** no canto superior interrompe fala e tarefas. Durante uma geração, **Parar** interrompe o turno atual. Uma operação do Windows já iniciada pode terminar; o cancelamento impede as etapas seguintes e descarta áudio e respostas atrasadas. Não existe desfazer universal para ações externas.

Comece com fone de ouvido para reduzir eco. A captura usa cancelamento de eco e redução de ruído do dispositivo de áudio; a qualidade com alto-falantes depende do ambiente. Em Configurações → Minha voz, escolha a voz masculina Piper ou uma voz feminina pt-BR já instalada no Windows, como Microsoft Maria. As duas funcionam localmente; a opção feminina fica indisponível quando o Windows não tem essa voz. “Ouvir minha voz” permite experimentar a seleção antes de salvar. A chamada por “Paçoca” é opcional e fica desligada inicialmente.

O reconhecimento **Rápida**, padrão desde a 1.3, usa Whisper base int8 com um thread de CPU. Para falas difíceis, escolha **Mais precisa**, que utiliza Whisper small e leva mais tempo. Os dois modelos acompanham a instalação; não há download durante a conversa. A transcrição e a resposta continuam locais. Aplicativos, jogos e serviços podem levar seu próprio tempo para abrir ou conectar.

## Memória e conhecimento

Em **Memória**, adicione, edite ou esqueça fatos e preferências. Na conversa, você também pode pedir para guardar algo: a Paçoca mostra o conteúdo e solicita autorização. O histórico de conversas é separado da memória pessoal; apagar uma lembrança não apaga as mensagens onde ela foi mencionada. Cada conversa pode ser removida pela lista lateral.

Em **Conhecimento**, adicione pastas e clique em **Atualizar índice**. A autorização vale para a pasta e suas subpastas. O aplicativo suporta texto, código, PDF com texto e DOCX. PDFs digitalizados sem texto não são submetidos a OCR nesta versão. Credenciais com nomes conhecidos e pastas de dependências são ignoradas. A leitura direta está limitada a 4 MB por arquivo; o índice processa até 1.000 documentos por pasta em cada atualização. A busca é textual local, não um serviço externo de embeddings.

Você pode perguntar “O que os documentos dizem sobre orçamento?”; a ferramenta retorna trechos com seus caminhos de origem. Remover uma pasta retira a permissão e o índice correspondente, preservando os arquivos originais.

## O que a Paçoca faz no computador

- Consulta data, hora, memória RAM e uso da CPU.
- Lista aplicativos do menu Iniciar e solicita a abertura de um aplicativo escolhido.
- Consulta janelas, muda o foco e lê controles por UI Automation.
- Preenche ou aciona controles observados, após aprovação.
- Consulta ou ajusta o volume.
- Lista, lê e abre documentos em pastas autorizadas.
- Cria ou substitui arquivos TXT, Markdown, JSON e CSV, após conferir o conteúdo e obter aprovação.
- Consulta o conhecimento indexado e as lembranças pessoais.
- Cria, consulta e cancela lembretes locais. O aplicativo precisa estar aberto para notificar.
- Opera um navegador próprio com páginas, abas, leitura, campos e cliques supervisionados.

As ferramentas verificam os resultados quando possível. Quando a janela não puder ser confirmada, a resposta deve informar que a solicitação foi enviada sem confirmação. O navegador usa um perfil separado, bloqueia acesso a endereços privados/locais e pede autorização para navegar ou alterar páginas. O conteúdo dos sites e documentos não concede permissões.

A Paçoca funciona na sessão atual do Windows. Tela bloqueada, UAC e aplicativos elevados podem impedir automação. Ela não executa texto livre gerado pelo modelo em um terminal. Não há garantia de automação para qualquer programa ou de acerto de todo pedido: as capacidades disponíveis estão no catálogo de ferramentas.

## Jogos e música

Exemplos de pedidos diretos:

- “Abre o Valorant.”
- “Abre o CS e entra no mata-mata.”
- “Abre o Spotify no PC.”
- “Toca Numb Linkin Park no PC.”
- “Abre o Spotify no PC, mas tocar Numb Linkin Park na Alexa.”
- “Agora transfere a música para a Alexa.”
- “Próxima música”, “pausa a música” ou “continua a música”.

Os aplicativos precisam estar instalados e suas contas conectadas. A Paçoca usa o catálogo do menu Iniciar; se um jogo não aparecer, escolha seu executável em **Configurações → Jogos e Spotify**. Ela confere a janela do jogo e libera o modelo antes de abrir Valorant ou CS2. O mata-mata usa o menu visível do CS2 e só é confirmado depois que o estado de busca aparece. Se o menu mudar, o foco sair ou uma partida já estiver aberta, o fluxo para e informa o que falta. Nenhum modo é escolhido por coordenadas fixas.

No Spotify, informe música e artista para reduzir ambiguidades. O programa busca na interface instalada, seleciona uma faixa única e confere os metadados de reprodução do Windows. Mais de um resultado exige um nome mais preciso. Os controles de mídia são dirigidos à sessão do Spotify; não são enviados ao player do navegador.

Você tem Premium. Para Alexa/celular, o dispositivo precisa aparecer no Spotify Connect: abra o Spotify no celular se ele estiver ausente, e confira sua Echo no seletor. Duas Echos exigem nome exato; uma preferência salva pode resolver a escolha. A troca só é confirmada quando a interface indica o dispositivo selecionado. O seletor precisa ficar visível durante a operação. A disponibilidade depende do Spotify e da rede. Isso controla a reprodução na Echo; falar com a Paçoca pela Alexa continua sendo a integração de skill descrita em ALEXA.md.

## Desempenho e atualizações

O modo leve usa Qwen3 1.7B quantizado em CPU, dois threads por padrão, limite de CPU e prioridade reduzida. Voz e transcrição ficam em um processo separado de um thread, sem processamento ONNX em espera. Ambos são encerrados após a inatividade configurada. O modelo 8B já existente é preservado, mas só carrega se você escolher **Avançado**. A proteção de jogos suspende esse modo enquanto processos conhecidos de jogos estiverem ativos. Um computador com pouca RAM livre pode recusar o carregamento para evitar paginação excessiva.

A Paçoca procura versões publicadas a cada seis horas, baixa o pacote e verifica assinatura e todos os arquivos. Ela aguarda uma oportunidade sem jogos, pedidos, sessão de voz, reprodução da resposta ou rascunho aberto; também pode instalar ao encerrar. O código do programa é atualizado sem baixar novamente os modelos. Antes da troca, o banco é copiado para backup. Se a nova janela não renderizar corretamente, os arquivos anteriores são restaurados. Não há repetição automática de uma versão que falhou.

Em **Configurações → Sempre por perto**, acompanhe o download, procure versões ou reinicie para atualizar quando estiver livre. O canal precisa ter uma versão compatível publicada pelo mantenedor. Sem rede, o programa continua funcionando com a versão instalada. Pacotes de atualização usam assinatura própria do projeto; o instalador ainda não tem certificado Authenticode do Windows.

## Atividades, dados e diagnóstico

**Atividades** registra o pedido, as ferramentas chamadas, decisões de autorização e resultado. Uma tarefa em execução durante uma falha do aplicativo reaparece como **Precisa de atenção**; ela não é repetida automaticamente. Lembretes aparecem na segunda aba.

**Configurações → Exportar minhas conversas** salva um JSON com histórico, memórias e preferências. A exportação permite backup e leitura; restauração automática desse JSON não está implementada. A desinstalação oferece preservar os dados ou apagá-los.

Dados pessoais ficam em `%LOCALAPPDATA%\Pacoca`, separados dos binários. O banco é `pacoca.sqlite3`. A pasta `Workspace` é o espaço de documentos. Os arquivos `pacoca.log` e `engine.log` ajudam no diagnóstico. Em **Ver diagnóstico**, é possível consultar o estado do modelo e as últimas mensagens do motor. O modo **Leve** usa CPU por padrão. **Liberar inteligência agora** encerra o motor e devolve seus recursos ao computador; o próximo pedido volta a carregá-lo. O modo avançado só aparece disponível se o modelo 8B estiver instalado.

O modelo de linguagem pode errar. Respostas de conversa devem ser avaliadas pelo conteúdo; ações importantes exibem os argumentos para decisão do usuário. Os modelos e a voz desta distribuição rodam localmente. Web e Alexa são integrações opcionais que usam rede.

## Para desenvolver

Em Windows, com Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements.lock
.\.venv\Scripts\python.exe scripts/prepare_assets.py
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m pacoca
```

Para construir o instalador completo:

```powershell
.\.venv\Scripts\python.exe scripts/build_release.py
```

O preparo de recursos baixa os modelos fixados em `packaging/assets.lock.json`, verifica SHA-256, extrai o motor e prepara o Chromium dedicado. O build usa PyInstaller e Inno Setup e gera `release/Pacoca-Setup.exe` e `release/SHA256SUMS.txt`. O modelo leve é provisionado por HTTPS com revisão e SHA-256 fixados. O 8B é um recurso opcional no mesmo instalador. Transcrição, voz, bibliotecas e navegador já acompanham o pacote. Não há download de modelo na inicialização do aplicativo. O código-fonte e os avisos de terceiros acompanham a instalação.

Para testes da base nova:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests_next -p pytest_asyncio.plugin -q
```

Os testes antigos continuam na pasta `tests/` como referência. Não são o critério de validação da aplicação recriada.

## Chamar pelo nome no PC (1.2.0)

Ative **Ouvir quando eu disser “Paçoca”** em Configurações, ou **Ativar “Paçoca”** acima da caixa de mensagem. Escolha o microfone correto. Diga “Paçoca, que horas são?” em uma única frase ou chame “Paçoca”, aguarde o sinal curto e faça seu pedido. Durante a sessão, fale normalmente, sem repetir o nome. O prazo para voltar à espera é configurável entre 10 e 60 segundos; tarefas, respostas, reprodução e decisões pendentes mantêm a sessão ativa.

O indicador **Diga “Paçoca” · escuta local** significa que o microfone está aberto. O aplicativo precisa continuar aberto; pode ficar minimizado. Fechar a janela encerra o aplicativo e a escuta. **Voltar à espera** mantém a escuta da palavra-chave; **Pausar microfone** fecha a captura e mantém essa preferência no próximo início. Há também **Pausar microfone** no ícone da bandeja. O botão de emergência fecha o microfone e interrompe as tarefas.

A espera usa apenas um detector pequeno de palavras, com prioridade reduzida e limite de CPU de 5% no Windows. Whisper e a IA de conversa continuam sob demanda e podem ser liberados por inatividade. O nome detectado é confirmado pela transcrição antes do primeiro pedido. O áudio de espera mantém no máximo quatro segundos em memória e segue apenas para o servidor do próprio aplicativo em 127.0.0.1; não é salvo nem enviado à nuvem.

Ajuste a sensibilidade se houver chamadas perdidas ou ativações por engano. O detector usa fonemas de um modelo acústico em inglês com pronúncias próprias de “Paçoca”; reconhecimento perfeito de vozes e sotaques brasileiros não foi comprovado. Os testes automatizados usam fala sintética. Não altera a palavra de ativação dos dispositivos Echo.
