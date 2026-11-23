# Verificação do backend

Em 20/11/2026 foi executado `python -m unittest discover -s server -v`, com 9 testes aprovados. A suite verifica estado inicial vazio e ação explícita de demo, reimportação idêntica sem duplicar avisos, atualização de reembolso no mesmo registro, separação de perfis, validação antes de mutação, rejeição de dinheiro NaN, análise sem timestamps fabricados, MIME inválido, upload excessivo e upload interrompido.

O áudio fornecido foi inspecionado por FFprobe e possui 30,986 segundos, com 80.121 bytes. FFmpeg e FFprobe estão instalados. Faster Whisper 1.2.1 e modelo tiny foram instalados em ambiente virtual. A transcrição real em português retornou 3 segmentos e levou 57,36 segundos, incluindo inicialização/download do modelo na primeira execução. O modelo tiny apresentou erros de palavras, então a transcrição precisa poder ser revisada pelo usuário. Não houve chamada de API paga. O custo monetário por vídeo depende da energia e hardware locais e não foi medido.

Integração TikTok, análise visual de quadros, Web Push com browser fechado e isolamento multiusuário não foram testados, pois ainda não estão implementados no backend. A análise semântica posterior à transcrição permanece heurística.

`server/verify_media.py` converteu o áudio fornecido em MP4 com fundo preto, subiu o binário por HTTP para `/api/videos`, validou resposta 200, transcrição temporizada, detecção de stream de vídeo e persistência de um relatório em banco isolado. A última execução terminou com código 0 e processamento de 14,89 segundos após cache do modelo. Mídia e banco de teste foram removidos ao final. A primeira execução identificou conexão SQLite aberta após uso de contexto; a correção passou na repetição e nos 9 testes unitários.

Para repetir, execute `.\.venv\Scripts\python.exe server/verify_media.py CAMINHO_DO_AUDIO`. O script mantém o áudio de origem e usa somente cópias temporárias próprias.

Frontend verificado com Chrome/Playwright após timeout do navegador integrado. Build TypeScript/Vite aprovado. Fluxos de demonstração, geração e salvamento de roteiro, cadastro de creator e upload/transcrição/relatório pela interface passaram sem exceções JavaScript. Viewports 1440x1000 e 375x812 inspecionados em screenshots. Overflow dos filtros móveis corrigido e teste repetido com scrollWidth <= innerWidth. A notificação local retornou sucesso na API com permissão concedida no contexto de teste, mas o Chrome headless não reteve notificação enumerável. Entrega visual pelo sistema operacional permanece sem comprovação. Web Push remoto contínuo segue pendente.

Comparação visual com as referências locais de produto: hierarquia de navegação, tipografia, contraste, tabelas e controles responsivos conferidos. Não houve mockup aprovado pelo usuário. A pesquisa Refero retornou NO_SUBSCRIPTION. Dados fictícios e importações ficam em seletores de fonte separados.
Cadastro com legenda, extração de hashtags únicas e métricas manuais com origem também passou no navegador. Envio de vídeo permanece bloqueado na interface até a autorização explícita do usuário.

## Conexões e backend em 21/11/2026

34 testes unitários/HTTP aprovados, incluindo os nove originais. A cobertura inclui login, sessão expirada, logout, throttle, Host/Origin, vínculo OAuth à sessão, retorno limpo, rejeição de identidade seller e escopos ausentes, cota diária de IA, rejeição de cenas com tempos inválidos e evidências inventadas, scanner e idempotência. O transporte de IA/OAuth usa respostas simuladas nos testes.

Web Push usa a biblioteca real para cifrar e assinar com VAPID, com transporte HTTP simulado. Também foram verificados ledger por evento/dispositivo, reivindicação concorrente por dois workers, backoff, remoção de endpoint expirado e cancelamento de inscrição. Isso não comprova entrega em um celular físico.

Na interface do navegador integrado foram conferidos login com senha sintética em instalação temporária isolada, importação automática de arquivo JSON pelo worker, GMV R$100 e comissão R$15, nova verificação sem alterações e logout retornando ao login. A instalação real permanece com o proprietário ainda sem senha escolhida pelo usuário. Dados sintéticos não são inseridos no banco real.

O build TypeScript/Vite passou. Docker/Compose não foram executados, pois Docker não está disponível. A autorização TikTok real e a leitura de métricas comerciais permanecem dependentes das credenciais, aprovação e contrato de API do proprietário.

Em 21/11/2026, a suite ampliada passou com 39 testes. Foram acrescentados testes de tokens Creator criptografados, bloqueio de modelos cloud no adaptador local, rejeição de alegações comerciais identificadas, planejamento temporal no servidor e substituição de quantidades ausentes com anotação no rascunho.

Ollama 0.40.16 foi instalado no usuário Windows, sem administrador. A descoberta Vulkan falhou inicialmente; o runtime com CPU ficou disponível após aproximadamente 69 segundos. O modelo qwen3:1.7b foi avaliado e apresentou extrapolações de benefícios. Foi baixado qwen3:4b e validada geração local em 141,69 segundos e análise textual em 121,81 segundos. O primeiro rascunho continha uma quantidade inventada, motivando o teste e o tratamento determinístico de números. Esses exemplos não formam um benchmark de qualidade. As saídas continuam exigindo revisão humana e a análise não mede engajamento real.

A tentativa de captura responsiva final do navegador integrado expirou após o serviço reinicializar. Os fluxos de login, scanner e logout haviam sido observados na própria interface. Nenhuma captura posterior foi apresentada como se tivesse sido obtida.

Teste final pelo endpoint real POST /api/ai/generate retornou HTTP 200 em 105,06 segundos com qwen3:4b em CPU, após remover exemplos descritivos do prompt que eram copiados como conteúdo pelo modelo. O resultado passou pelos validadores e foi salvo por POST /api/scripts com provider, model, method e usage. O histórico identifica esse registro como exemplo de teste. Foram retornados 376 tokens de entrada e 379 de saída. Ganchos duplicados e respostas que repetem instruções são rejeitados.

A versão final mantém revisão humana obrigatória para a qualidade e precisão editorial. Validadores determinísticos não comprovam todos os significados do texto. Não houve chamada OpenAI paga ou envio de dados ao TikTok com credenciais reais.
Verificação final em 21/11/2026 — 41 testes aprovados. O uso local foi separado da cota remota. Chamadas Ollama registram uso e não consomem o limite OpenAI. Build TypeScript/Vite e compilação Python aprovados. Servidor reiniciado com a configuração final.

## Revisão dos fluxos
A interface foi verificada com Chrome e Playwright em largura de 375 px. A importação CSV contou dois itens associados como um único pedido, o filtro Hoje excluiu registro antigo e o formulário de transcrição manual abriu o relatório com uma única autorização. A renderização permaneceu dentro da largura da tela.
Um upload local de vídeo com áudio transcrito e uma transição controlada retornou HTTP 200. O FFmpeg detectou a mudança em 1,00 s. Com a falha de IA simulada, o backend persistiu a transcrição, as métricas visuais e o relatório local.
A pesquisa oficial confirmou o recurso Search Creator Affiliate Orders e seu grupo de escopos. A página da versão completa depende de JavaScript e a evidência disponível não confirma o contrato financeiro nem o acesso do aplicativo no Brasil.
