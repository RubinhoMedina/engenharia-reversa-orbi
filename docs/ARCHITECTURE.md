# Arquitetura

React/Vite e TypeScript compõem a interface. O backend Python serve o build e as APIs HTTP. SQLite mantém um workspace de proprietário único. O padrão local preserva o banco legado server/orbit.sqlite3. ORBIT_DATABASE_PATH permite outro caminho e volume persistente em hospedagem.

O carregador de .env usa valores literais, sem executar comandos. A configuração do processo prevalece. O assistente usa entrada local e grava arquivos privados. Segredos não são expostos por /api/integrations.

Autenticação usa senha scrypt, sessões opacas com hash no banco, cookies HttpOnly/SameSite=Lax e expiração configurável. Host/Origin e Content-Type são verificados nas mutações. O acesso de rede pública exige senha e origem HTTPS configuradas. A instalação atende um proprietário e ainda não oferece isolamento SaaS multiusuário.

FFprobe valida a mídia; FFmpeg extrai áudio; Faster Whisper tiny CPU int8 retorna transcrição temporizada. Os originais e WAV são temporários. O modelo de transcrição é serializado por trava. O processamento continua síncrono e limitado a 180 segundos/100 MB.

O módulo ai.py oferece regras, Ollama loopback e OpenAI Responses. A conexão remota fica desabilitada por padrão. O adaptador valida listas, cenas/tempos e evidências textuais. Citações ausentes no texto são rejeitadas. O limite diário remoto é reservado atomicamente em SQLite e inclui falhas. Uso Ollama é registrado separadamente, sem consumir a cota OpenAI. Saídas registram motor, modelo e uso de tokens quando fornecido. Falha de provedor não é disfarçada como resposta de IA.

O módulo commerce.py implementa OAuth Creator conforme documentação pública, state aleatório de uso único vinculado à sessão e validação de user_type e escopos. Tokens são cifrados no cofre local. A renovação revalida identidade. A leitura oficial de pedidos e o mapeamento financeiro permanecem dependentes de endpoint, contrato e cobertura habilitados para o aplicativo aprovado.

O scanner de exportações roda no worker e recebe CSV e JSON canônicos do proprietário. Valida todos os registros de cada arquivo antes de escrever, usa identificadores por fonte/conta/item e ignora conteúdo idêntico. Importações preservam origem manual e avisos de teste. Cancelamentos e alterações atualizam o registro da fonte.

O worker Web Push usa subscriptions criptografadas, VAPID e biblioteca pywebpush. O ledger por evento/dispositivo usa lease, tentativas limitadas e backoff. Endpoints 404/410 são removidos. Avisos anteriores à inscrição do dispositivo são ignorados. Repetição após queda entre envio e persistência é possível e a tag estável mitiga duplicação visual. O Service Worker recebe o evento e apresenta a mensagem.

Docker/Compose/Caddy preparam uma implantação de um proprietário com backend permanente, disco e cache Whisper persistentes e proxy HTTPS. A execução dessa implantação permanece sem teste nesta máquina sem Docker. O adaptador Ollama limita origem a loopback por padrão e aceita hosts explicitamente autorizados pelo operador. O perfil local-ai do Compose oferece um Ollama privado em CPU, com volume próprio de modelos.

MCP/REA foi usado no desenvolvimento e investigação. O aplicativo usa seus próprios contratos HTTP e credenciais. Nenhum acesso de MCP do chat é herdado pela instalação.
