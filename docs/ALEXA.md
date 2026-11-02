# Conectar a Paçoca à Alexa

A integração é opcional. Conversa, voz e memória no PC funcionam sem ela. O Echo usa os serviços da Amazon; a experiência e os prazos de uma custom skill são diferentes de uma sessão local de voz.

## Configurar a skill

1. Na Alexa Developer Console, crie uma **custom skill** no idioma **Português (BR)**.
2. Importe o modelo de interação incluído em `alexa/pt-BR.json` na instalação, ou `packaging/alexa/pt-BR.json` no código-fonte.
3. O nome inicial de invocação é **paçoca assistente**; valide o reconhecimento e as regras de publicação no console.
4. Configure um endpoint HTTPS que encaminhe **somente POST /alexa** para o servidor da Paçoca no PC. O proxy precisa reescrever o cabeçalho Host para o endereço local e não pode publicar `/api/`, `/events` ou a interface.
5. Em **Configurações → Alexa**, informe o Skill ID e o User ID da sua própria conta da skill, e ative a integração.
6. No console, habilite os testes e use a mesma conta registrada no Echo.

Para uma porta estável no PC, a Paçoca aceita `Pacoca.exe --port 7811`. O destino local do proxy será `http://127.0.0.1:7811/alexa`. A conexão pública deve usar HTTPS. Esta versão inclui o adaptador e o modelo da skill; não provisiona uma conta Amazon, domínio, túnel ou hospedagem. Nenhum serviço pago é ativado pelo aplicativo.

Exemplo de configuração de proxy Nginx (adapte certificado, domínio e rede):

```nginx
location = /alexa {
    limit_except POST { deny all; }
    client_max_body_size 100k;
    proxy_set_header Host 127.0.0.1:7811;
    proxy_pass http://127.0.0.1:7811/alexa;
}
location / { return 404; }
```

O Nginx é um exemplo para infraestrutura externa, não uma dependência do aplicativo instalado. A escolha de um túnel ou proxy depende da sua rede. Não exponha diretamente o servidor local da Paçoca à internet.

## Usar

- “Alexa, abrir paçoca assistente.”
- Dentro da skill: “Executar consultar o volume do computador.”
- “Como está meu pedido?”
- “Parar.”

Pedidos são enfileirados e recebem confirmação de recebimento rapidamente. Consulte o resultado depois. A confirmação inicial não significa que a tarefa terminou. O endpoint trata intents e slots; não recebe um fluxo contínuo do microfone do Echo.

Nesta distribuição, o canal Alexa permite consulta de hora, informações do computador, volume e lembretes. Operações de arquivo, navegador e interação com aplicativos precisam da janela da Paçoca. A parada pela Alexa afeta pedidos feitos por esse canal e preserva os turnos do desktop.

## Verificações implementadas

- Assinatura e cadeia de certificado Amazon pelo SDK oficial.
- Timestamp com tolerância de 150 segundos.
- Skill ID e usuário explicitamente vinculados.
- Deduplicação persistente por request ID.
- Sessão e restrições próprias do canal.
- Integração desativada quando IDs não estão configurados.

Os testes automatizados cobrem rejeição de requisições sem assinatura, usuário divergente, timestamp expirado, integração desativada e deduplicação após validação simulada. A validação de ponta a ponta no Echo exige sua conta, skill e endpoint HTTPS e não é substituída por esses testes.
