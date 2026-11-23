# Orbit Creator Commerce

Workspace de um proprietário para pedidos e comissões, análise de vídeo, roteiros e pesquisa de creators. Frontend React/TypeScript, API Python, SQLite, FFmpeg, Faster Whisper, adaptadores de IA e worker Web Push.

## Executar

No PowerShell, nesta pasta, execute `./Install-Orbit.ps1` para instalar dependências e compilar. Nesta máquina o ambiente já está preparado. Execute `./Start-Orbit.ps1` e abra http://127.0.0.1:8787.

Execute `./Configure-Orbit.ps1` para conectar um motor por vez. O assistente preserva as outras configurações e guarda segredos no `.env` local ignorado pelo Git. Reinicie o servidor após alterações. Em **Conta e fontes**, consulte o diagnóstico e teste os motores.

| Motor | Configuração | Recurso |
| --- | --- | --- |
| Acesso | Assistente, opção 5 | Senha scrypt, sessão HttpOnly, expiração e throttle |
| IA local | Opção 1, Ollama e modelo instalado | Geração personalizada e análise da transcrição |
| IA OpenAI | Opção 1, chave/modelo e habilitação explícita | Responses API com uso de tokens e limite diário de chamadas |
| Transcrição | FFmpeg no PATH e dependências Python | Whisper tiny local com segmentos temporizados |
| TikTok Creator | Opção 2, aplicativo aprovado e escopos concedidos | OAuth com state vinculado à sessão, tokens criptografados e renovação |
| Exportações | Opção 3, pasta CSV ou JSON | Scanner a cada 60 segundos, conciliação e diagnóstico |
| Web Push | Opção 6, contato VAPID | Inscrição consentida, fila, repetição e revogação |
| Acesso remoto | Opção 4, domínio HTTPS e hospedagem | Backend e worker permanentes com disco persistente |

Em **Criar conteúdo**, escolha entre modelo editorial e IA conectada. A análise de vídeo usa o motor configurado no servidor. Falhas externas são retornadas sem fingir um resultado de IA.

## Pedidos próprios

`POST /api/orders/import` recebe `{"orders":[...]}`. A pasta automática aceita esse objeto ou uma lista direta. Cada item JSON precisa de `id`, `product` e `gmv`. No painel, use o modelo CSV para preencher os cabeçalhos completos. O guia de conexões detalha os dois formatos.

Status aceitos são `pago`, `pendente`, `cancelado`, `reembolsado`. Comissões usam `estimada`, `aprovada`, `liquidada`. Valores em BRL. Para pedidos com múltiplos itens, forneça um `id` estável por item e o mesmo `order_id` em todos eles. Atualize o mesmo identificador para reembolsos e mudanças de comissão. Registros repetidos sem alterações não geram novos avisos internos.

Demo é opt-in e usa origem `demo`. Dados próprios importados usam `manual`, inclusive via pasta automática. O seletor mantém os totais independentes. Exportações de outros sistemas precisam ser convertidas para o contrato JSON do Orbit.

## Cobertura atual

OAuth TikTok está implementado. A leitura automática de pedidos oficiais ainda exige confirmar endpoint, versão, campos, permissões e mercado BR no aplicativo aprovado do proprietário. Autorizar a identidade Creator não comprova acesso a todas as métricas. Nenhuma credencial TikTok foi fornecida nesta sessão.

Creators são pesquisados no acervo do proprietário. GMV, vendas, comissões e parcerias de terceiros exigem fonte autorizada ou exportação identificada. Não há fornecedor licenciado dessas métricas conectado.

O áudio enviado foi transcrito com Whisper tiny, que pode trocar palavras. A IA analisa texto e tempos reconhecidos. O FFmpeg estima mudanças visuais a 8 quadros por segundo e apresenta os tempos detectados. A interpretação das imagens e da entonação exige revisão humana. Quando o motor de IA falha no upload, a transcrição e o relatório local são preservados. Os arquivos de mídia são temporários e removidos após processamento. Transcrições e relatórios persistem no SQLite.

Chamadas OpenAI ficam desabilitadas até configuração explícita. O limite diário restringe chamadas OpenAI em UTC, incluindo tentativas que falharam, e não constitui teto monetário. O uso local é registrado separadamente e não consome essa cota. Configure os controles de orçamento da conta. O custo de energia local não foi medido.

Web Push usa pywebpush. Testes cobrem assinatura e criptografia reais com transporte simulado. Entrega em celular físico exige HTTPS, consentimento e inscrição naquele dispositivo. No iPhone, instale pelo Safari na Tela de Início em versão compatível. O servidor precisa permanecer ativo. Identificadores estáveis mitigam repetição após falhas. Avisos de demo/importação são rotulados como teste de atualização.

A senha protege um workspace inteiro de um proprietário. Perfis comerciais não criam contas isoladas para clientes diferentes. Um SaaS multiusuário exige evolução da autorização e do isolamento.

A pasta `supabase/` contém a migração inicial de dados por usuário e o teste PostgreSQL das políticas de acesso. O aplicativo ainda usa SQLite na execução local. Ativar o SaaS exige conectar o login Supabase e ligar as rotas e os processos em segundo plano a usuários autenticados.

MCP/REA apoiou a investigação de referência. O aplicativo funciona com APIs HTTP, bibliotecas locais e worker próprio. As conexões deste chat não são transferidas automaticamente ao Orbit.

## Hospedagem e testes

Consulte [conexões e ativação](docs/CONNECTIONS.md). Dockerfile, Compose e Caddy preparam backend, armazenamento persistente e HTTPS. Docker não está disponível nesta máquina, portanto essa implantação permanece sem execução. Nenhum serviço foi publicado ou comprado.

Execute `./.venv/Scripts/python.exe -m unittest discover -s server -v` e `npm run build`. Consulte [relatório de validação](docs/TEST_REPORT.md) para a cobertura, testes simulados e limites.

Nesta máquina foi instalado Ollama 0.40.16 no usuário Windows e configurado qwen3:4b em CPU. Os testes locais de geração e análise levaram cerca de dois minutos por chamada. O modelo menor 1.7b também foi baixado para avaliação. A inicialização de hardware pode levar mais de um minuto. Start-Orbit.ps1 inicia o runtime instalado quando necessário. ORBIT_OLLAMA_CPU permite controlar o modo CPU. A pasta de importação inicial é server/data/imports, já criada e ignorada pelo Git.

Conteúdo de IA é rascunho. O backend rejeita alegações comerciais identificadas sem suporte, corrige quantidades inventadas com anotação e valida evidências textuais. A revisão humana continua necessária para precisão e qualidade editorial.
