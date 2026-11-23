"""Interactive local setup. Credentials never go through a browser or chat."""
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
import config
from auth import private_write


def ask(label, current='', secret=False):
    suffix = ' [Enter mantém o atual]' if current else ' [opcional]'
    value = (getpass.getpass if secret else input)(label + suffix + ': ').strip()
    if '\n' in value or '\r' in value:
        raise ValueError('Configuração inválida.')
    return value or current


def write_environment(values):
    target = config.ROOT / '.env'
    lines = target.read_text(encoding='utf-8-sig').splitlines() if target.exists() else []
    rewritten = []
    pending = dict(values)
    for line in lines:
        key, separator, _ = line.partition('=')
        if separator and key.strip() in pending:
            key = key.strip()
            rewritten.append(key + '=' + pending.pop(key))
        else:
            rewritten.append(line)
    rewritten.extend(key + '=' + value for key, value in pending.items())
    directory = config.ROOT / 'server' / 'data'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        path = Path(temporary) / 'environment'
        private_write(path, '\n'.join(rewritten) + '\n')
        os.replace(path, target)


def main():
    config.load_dotenv()
    print('Configuração ORBIT. Os segredos serão guardados somente no .env local ignorado pelo Git.')
    print('1 — Inteligência\n2 — TikTok Creator OAuth\n3 — Importação automática\n4 — Domínio público\n5 — Senha de acesso\n6 — Notificações Web Push')
    choice = input('Escolha uma conexão: ').strip()
    values = {}
    if choice == '1':
        provider = input('Motor (rules / ollama / openai): ').strip().lower()
        if provider not in {'rules', 'ollama', 'openai'}:
            raise ValueError('Motor inválido.')
        values['ORBIT_AI_PROVIDER'] = provider
        if provider == 'ollama':
            values['OLLAMA_MODEL'] = ask('Nome exato do modelo local', os.getenv('OLLAMA_MODEL', ''))
            values['OLLAMA_BASE_URL'] = 'http://127.0.0.1:11434'
        if provider == 'openai':
            print('A API pode gerar cobrança. Configure orçamento na sua conta OpenAI antes de habilitar.')
            values['OPENAI_API_KEY'] = ask('Chave OpenAI', os.getenv('OPENAI_API_KEY', ''), True)
            values['OPENAI_MODEL'] = ask('ID do modelo disponível', os.getenv('OPENAI_MODEL', ''))
            values['ORBIT_AI_DAILY_REQUEST_LIMIT'] = ask('Máximo de chamadas por dia UTC', os.getenv('ORBIT_AI_DAILY_REQUEST_LIMIT', '20'))
            consent = input('Autoriza chamadas pagas deste app com essa configuração? Digite HABILITAR: ')
            values['ORBIT_AI_REMOTE_ENABLED'] = 'true' if consent == 'HABILITAR' else 'false'
    elif choice == '2':
        print('Use as credenciais do aplicativo aprovado e escopos Creator do Partner Center.')
        for name, label, secret in [('TIKTOK_APP_KEY', 'App Key', False), ('TIKTOK_APP_SECRET', 'App Secret', True),
                                    ('TIKTOK_REDIRECT_URI', 'Redirect URI /api/commerce/tiktok/callback', False),
                                    ('TIKTOK_REQUIRED_SCOPES', 'Chaves de escopos aprovados, separadas por vírgulas', False)]:
            values[name] = ask(label, os.getenv(name, ''), secret)
    elif choice == '3':
        directory = ask('Pasta com exportações JSON compatíveis', os.getenv('ORBIT_IMPORT_DIRECTORY', ''))
        if not directory or not Path(directory).is_dir():
            raise ValueError('Selecione uma pasta existente.')
        values['ORBIT_IMPORT_DIRECTORY'] = str(Path(directory).resolve())
        values['ORBIT_IMPORT_INTERVAL_SECONDS'] = '60'
    elif choice == '4':
        origin = ask('Origem pública HTTPS, sem caminho', os.getenv('PUBLIC_URL', ''))
        parsed = urlparse(origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Informe somente a origem HTTPS, como https://orbit.seudominio.com.')
        values['PUBLIC_URL'] = origin.rstrip('/')
        values['ORBIT_DOMAIN'] = parsed.hostname
    elif choice == '5':
        subprocess.run([sys.executable, str(config.ROOT / 'server' / 'auth.py')], check=True)
        return
    elif choice == '6':
        subject = input('Contato VAPID (mailto:seu@email ou domínio HTTPS): ').strip()
        subprocess.run([sys.executable, str(config.ROOT / 'server' / 'push.py'), '--subject', subject], check=True)
        return
    else:
        raise ValueError('Escolha inválida.')
    write_environment(values)
    print('Configuração salva. Reinicie o ORBIT e use Conta e fontes para testar a conexão.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
