# Escopo do MVP

A instalação atual atende um proprietário. O frontend oferece Início, Analisar Vídeo, Criar Conteúdo, Creators e Conta e fontes.

Vendas e comissões usam importação própria de CSV e JSON e demonstração opt-in, com origem separada, reconciliação por conta/identificador/item e atualização de cancelamentos/reembolsos. A pasta automática já está preparada em server/data/imports nesta máquina. O backend verifica arquivos a cada 60 segundos.

Vídeos próprios ou autorizados são transcritos com Whisper tiny local. Texto e tempos alimentam regras ou IA conectada. O relatório identifica o motor e seus limites. A transcrição pode conter erros. O FFmpeg estima mudanças visuais por diferença de quadros. A interpretação visual e a análise de entonação permanecem pendentes.

Roteiros têm três ângulos, três ganchos, três cenas com planejamento temporal, CTA, legendas e hashtags. A IA escreve conteúdo; o backend distribui a duração em gancho, demonstração e fechamento. Alegações promocionais identificadas sem suporte são rejeitadas. Quantidades não fornecidas são substituídas por texto editorial fundamentado e essa intervenção é anotada. A revisão humana continua necessária.

Pesquisa de creators usa o acervo fornecido pelo proprietário, com URLs, legendas, hashtags e métricas acompanhadas da origem informada. APIs de métricas comerciais de terceiros dependem de acesso oficial ou fornecedor licenciado.

Autenticação do proprietário, configuração local, diagnóstico das conexões, cofre de tokens, OAuth Creator e renovação estão implementados. Pedidos financeiros oficiais do TikTok aguardam confirmação de endpoint, contrato, escopos e cobertura BR no aplicativo aprovado. O fluxo real OAuth ainda não foi autorizado pelo proprietário.

Web Push possui fila persistente e transporte de envio, subscriptions criptografadas, VAPID, repetição e revogação. A ativação requer contato VAPID e inscrição consentida no dispositivo. Entrega física com navegador fechado permanece pendente de validação no celular do proprietário e hospedagem HTTPS.

Docker/Caddy preparam uma implantação de proprietário único com armazenamento persistente e Ollama opcional em serviço privado. Essa implantação não foi executada nesta máquina. Múltiplos clientes SaaS, publicação automática, billing comercial e MCP público permanecem fora da implementação atual.
