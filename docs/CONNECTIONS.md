# Conexões e ativação

| Objetivo | Acesso necessário | Implementação atual |
| --- | --- | --- |
| IA personalizada | Ollama e modelo local ou chave OpenAI/modelo com chamadas habilitadas | Adaptadores, teste de conexão, validação de saída e limite diário |
| Pedidos oficiais | Aplicativo TikTok Affiliate Creator aprovado, mercado BR, credenciais, callback e escopos | OAuth e renovação. Endpoint e mapeamento financeiro aguardam contrato aprovado |
| Exportações contínuas | Pasta de arquivos próprios em CSV ou JSON no formato Orbit | Scanner, conciliação e diagnóstico |
| Métricas de outros creators | API elegível ou fornecedor licenciado | Acervo manual e campos com origem. Fornecedor externo ausente |
| Avisos no celular | Chaves VAPID, inscrição consentida e servidor ativo | Transporte, fila, repetição e revogação |
| Acesso protegido | Senha do proprietário | Sessão, expiração e throttle |
| Uso remoto | Domínio HTTPS, servidor e disco persistente | Arquivos de implantação preparados. Publicação pendente |

## Configuração local

1. Execute `Configure-Orbit.ps1`, opção 5, para criar sua senha no terminal local.
2. Escolha 1 para selecionar a IA. No Ollama, mantenha o serviço em `http://127.0.0.1:11434` com o modelo instalado. Na OpenAI, forneça chave, modelo e habilite explicitamente chamadas remotas.
3. Escolha 3 para configurar a pasta de CSV e JSON. O scanner mantém os originais e verifica até 100 arquivos por rodada. Arquivos em gravação recente são adiados. Reexportações idênticas são ignoradas.
4. Escolha 6 para criar VAPID com contato `mailto:` ou URL HTTPS do responsável.
5. Reinicie `Start-Orbit.ps1`. Abra **Conta e fontes** para testar a IA e inscrever seu dispositivo em Web Push.
6. Para OAuth, preencha a opção 2 com seu aplicativo aprovado. Cadastre `https://SEU_DOMINIO/api/commerce/tiktok/callback` no Partner Center. Use **Autorizar no TikTok** no Orbit.

Credenciais ficam somente no `.env` local e cofre do servidor. Não envie segredos ao chat, frontend ou Git. Variáveis do processo prevalecem sobre `.env`. Reinicie o servidor após alterações.

## Contrato das exportações

```json
{
  "orders": [{
    "id": "pedido-123-item-1",
    "product": "Produto próprio",
    "account": "Minha conta",
    "date": "2026-11-21T10:00:00-03:00",
    "quantity": 1,
    "gmv": 100,
    "commission": 15,
    "status": "pago",
    "commission_status": "estimada"
  }]
}
```

Use um identificador `id` estável por item e conta. Use o mesmo `order_id` em linhas que pertencem ao mesmo pedido. O CSV usa cabeçalhos do modelo disponível no painel, com `order_id` opcional. Salve como UTF-8, com vírgula ou ponto e vírgula. Em dinheiro, use até duas casas decimais sem separador de milhar. Não se presume que um CSV ou exportação original do TikTok tenha esse formato. A conversão deve preservar identificadores e significado dos campos.

## APIs implementadas

| Método | Rota | Função |
| --- | --- | --- |
| GET | `/api/health` | Estado de execução sem identidade ou segredos |
| GET | `/api/auth/status` | Estado da sessão |
| POST | `/api/auth/login`, `/api/auth/logout` | Autenticar e revogar sessão |
| GET | `/api/integrations` | Diagnóstico sanitizado |
| GET | `/api/state` | Dados e históricos |
| POST | `/api/ai/test` | Consultar disponibilidade sem gerar conteúdo |
| POST | `/api/ai/generate` | Ângulos, ganchos, cenas, CTA e legendas |
| POST | `/api/videos`, `/api/analyses` | Transcrever mídia ou analisar texto |
| POST | `/api/orders/import` | Conciliar exportação própria |
| POST | `/api/commerce/imports/scan` | Verificar pasta configurada |
| POST | `/api/commerce/tiktok/start` | Iniciar OAuth Creator |
| GET | `/api/commerce/tiktok/callback` | Validar state e guardar tokens criptografados |
| POST | `/api/commerce/tiktok/refresh`, `/api/commerce/tiktok/disconnect` | Renovar ou remover credenciais locais |
| GET | `/api/push/config` | Chave pública e diagnóstico de entregas |
| POST | `/api/push/subscribe`, `/api/push/unsubscribe` | Registrar e remover dispositivo |
| POST | `/api/push/test` | Enfileirar teste |
| POST | `/api/scripts`, `/api/creators` | Persistir conteúdo e referências |

Rotas de dados exigem sessão quando há senha configurada. Backend valida Host, Origin e tipo de conteúdo. Callback evita registrar código OAuth nos logs. Tokens de seller e creator pertencem a identidades distintas.

## Implantação para um proprietário

Os arquivos Docker/Caddy precisam ser validados no servidor escolhido antes do uso cotidiano. Nenhuma implantação foi executada nesta sessão.

1. Configure Docker/Compose no servidor, DNS do domínio e portas 80/443.
2. Crie `.env` com `ORBIT_DOMAIN=seu.dominio`, `PUBLIC_URL=https://seu.dominio`, `ORBIT_DATA_DIR=/app/server/data` e `ORBIT_DATABASE_PATH=/app/server/data/orbit.sqlite3`.
3. Execute `docker compose build`.
4. Crie a senha no volume com `docker compose run --rm app python server/auth.py`.
5. Gere VAPID com `docker compose run --rm app python server/push.py --subject mailto:SEU_EMAIL`.
6. Após aprovação da publicação, execute `docker compose up -d`. Confirme certificado, login e entrega física de notificação.
7. Faça backups protegidos do volume, `.env` e chaves privadas. Preserve a chave do cofre para recuperar tokens.

O backend recusa acesso público sem senha e PUBLIC_URL HTTPS. A porta 8787 fica interna ao Compose. O proxy publica 80/443. Whisper usa cache persistente. O adaptador Ollama aceita loopback e hosts autorizados explicitamente no servidor. O Compose autoriza o serviço privado ollama e mantém sua porta interna. Para usar IA local no servidor, execute docker compose --profile local-ai up -d ollama e depois docker compose --profile local-ai exec ollama ollama pull qwen3:4b. Inicie os demais serviços após configurar senha e VAPID. O servidor precisa de RAM e CPU suficientes para o modelo. OpenAI pode ser usada após configuração e habilitação de chamadas.

## Fontes

A autorização e as permissões variam conforme aplicativo e mercado. [Guia TikTok Creator](https://partner.tiktokshop.com/docv2/page/678e3a362dccb8030ea6f98c)

A API Affiliate exige aprovação e separa recursos de seller, creator e parceiro. [Guia Affiliate](https://partner.tiktokshop.com/docv2/page/affiliate-integration)

O motor Ollama usa `/api/chat` e respostas JSON. [API Ollama](https://docs.ollama.com/api/chat)

O adaptador OpenAI usa Responses API. [Referência Responses](https://developers.openai.com/api/reference/resources/responses/methods/create)

Web Push requer inscrição e suporte do navegador. [Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API)
