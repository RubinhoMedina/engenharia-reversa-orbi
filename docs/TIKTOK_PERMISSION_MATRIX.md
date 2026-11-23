# Matriz de acesso TikTok

Verificação realizada em 20/11/2026. Nenhuma credencial de aplicativo, aprovação ou conta conectada foi fornecida nesta sessão.

| Objetivo | API candidata | Papel e escopo | Autorização e cobertura BR | Situação local | Atualização e limites | Dados e fonte |
| --- | --- | --- | --- | --- | --- | --- |
| Identificar usuário | TikTok Login Kit | Usuário, `user.info.basic` | Cadastro do aplicativo, configuração e consentimento. Dados adicionais exigem aprovação prévia. A fonte consultada não detalha recorte BR. | Sem app aprovado e sem teste OAuth | Não medidos | Nome e avatar. [Documentação oficial](https://developers.tiktok.com/docs/en/login-kit-overview) |
| Vendas e comissão de creator | TikTok Shop Affiliate Integration | Creator/partner, endpoint e escopos pendentes de verificação | Cobertura e aprovação BR não verificadas | Bloqueada por ausência de autorização e documentação acessível nesta sessão | Frequência e limites desconhecidos | [Documento candidato oficial](https://partner.tiktokshop.com/docv2/page/affiliate-integration) retornou timeout na consulta |
| Eventos de comissão | API/webhook específico de afiliados | Escopo desconhecido | Exige comprovação documental e autorização | Nenhum webhook integrado | Desconhecidos | Sem fonte acessível que confirme o evento necessário |
| GMV e comissões de terceiros | API oficial/parceiro licenciado a confirmar | Desconhecido | Acesso específico necessário | Campos ausentes ficam indisponíveis | Desconhecidos | Sem fonte licenciada configurada |

A documentação consultada descreve Login Kit como autenticação e acesso a dados básicos. Ela não comprova permissão para ler pedidos ou comissões de afiliados. Não foi assumida equivalência entre permissões de seller e creator.

Em 21/11/2026 a documentação pública de Creator Authorization e Affiliate Integration ficou acessível via busca. Foi implementado o fluxo OAuth Creator com URL shop.tiktok.com/alliance/creator/auth, state, callback, troca de código e renovação no host auth.tiktok-shops.com. Tokens exigem user_type Creator e escopos configurados a partir da aprovação específica do aplicativo. Os testes usam respostas simuladas e não estabelecem acesso real concedido.

O guia público mapeia Search Creator Affiliate Orders ao grupo Read Creator Affiliate Collaborations. A versão do endpoint e o contrato exato de pedidos/comissão para o app e mercado Brasil ainda não foram obtidos. A integração financeira oficial permanece pendente. O código não substitui isso por pedidos de seller nem inventa estados de comissão liquidada.

Fontes consultadas em 21/11/2026 — https://partner.tiktokshop.com/docv2/page/678e3a362dccb8030ea6f98c e https://partner.tiktokshop.com/docv2/page/affiliate-integration .
