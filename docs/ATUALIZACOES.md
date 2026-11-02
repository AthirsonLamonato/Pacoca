# Atualizações da Paçoca

A versão instalada consulta `https://github.com/AthirsonLamonato/Pacoca/releases/latest/download/desktop-update.json`. O manifesto e os pacotes contêm somente dados e arquivos da aplicação; não fornecem comandos para execução. A chave pública de confiança está em `src/pacoca/update_trust.py` e `packaging/update-public-key.json`.

O download pode continuar depois de uma interrupção. Antes de instalar, o aplicativo confere a assinatura RSA/SHA-256, o hash do ZIP e cada arquivo. O auxiliar confere tudo novamente, espera o processo original encerrar, obtém o bloqueio da instância e substitui somente `Pacoca.exe`, `_internal/` e os guias permitidos. Os modelos externos em `assets/`, Workspace, conversas e preferências ficam fora do pacote. Desde a 1.3, o runtime inclui o modelo pequeno de reconhecimento de fala em `_internal/speech/`; os modelos de conversa permanecem externos e são preservados.

A atualização normal é pequena: o executável com os módulos Python e os arquivos próprios da Paçoca. Quando bibliotecas, Python ou recursos de voz empacotados mudam, o manifesto oferece também o runtime completo. A identidade considera os locks de dependências, do detector de chamada e do reconhecimento de fala, a versão de Python e o formato de empacotamento. A primeira atualização para a 1.3 usa o runtime completo para entregar o reconhecimento rápido; atualizações seguintes com a mesma identidade podem usar somente o pacote pequeno da aplicação.

Antes da troca é feito backup consistente do banco SQLite. O instalador reinicia a janela e espera a confirmação de renderização real do QtWebEngine, conexão ao servidor, versão e PID esperados. Falha nesse diagnóstico restaura os arquivos anteriores. Dados pessoais não são sobrescritos pelo rollback. O resultado fica em `%LOCALAPPDATA%\Pacoca\Updates\last-result.json`. Uma versão que falhou não entra em um ciclo automático de reinstalação.

## Publicar uma versão

1. Atualize a versão em `src/pacoca/__init__.py`, `pyproject.toml`, `packaging/version.txt` e `packaging/installer.iss`.
2. Execute os testes e `scripts/build_release.py`. O build exige verificação de correspondência entre código e executável e teste de janela nativa.
3. Execute `scripts/package_update.py`, que gera `Pacoca-VERSAO-app.zip`, `Pacoca-VERSAO-runtime.zip` e `desktop-update.json`, usando a chave privada local do mantenedor. Ele valida a assinatura contra a chave pública já distribuída antes de concluir.
4. Publique uma release estável `vVERSAO` no repositório oficial com esses três arquivos, `Pacoca-Setup.exe`, `SHA256SUMS.txt` e `Pacoca-sources-VERSAO.zip` com o código-fonte e os avisos correspondentes. A release precisa ser marcada como Latest para alimentar o canal automático. Uma release em rascunho não ativa o canal.
5. Baixe o manifesto pelo endereço público usado pela aplicação, valide a assinatura e compare os hashes públicos dos arquivos com os arquivos locais.

Exemplo de preparo local:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests_next -p pytest_asyncio.plugin -q
.\.venv\Scripts\python.exe scripts/build_release.py
.\.venv\Scripts\python.exe scripts/package_update.py
```

A chave privada fica em `.tools/update-signing-key.pem`, fora do controle de versão e dos pacotes. Faça uma cópia protegida em local separado. Não gere outra chave para uma atualização comum: instalações existentes só confiam na chave já distribuída. O script `create_update_key.py` é para a criação inicial; não substitui uma chave existente silenciosamente. A assinatura dos pacotes é independente do certificado Authenticode do Windows.

## Evidências locais

`check_update_transaction.py` testa o auxiliar real com executáveis descartáveis: sucesso, assinatura inválida e rollback por executável inválido. `check_real_update.py` testa a troca automática entre distribuições reais 1.1.0 e 1.1.1, usando um feed HTTP restrito a localhost e a mesma assinatura exigida em produção. O teste local não comprova a publicação ou a disponibilidade do canal público do GitHub.
