"""Single owner authentication with hashed password and opaque sessions."""
import argparse
import base64
import getpass
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import os
from pathlib import Path
import secrets
import threading
import time
import subprocess
import config

COOKIE = 'orbit_session'


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        output.write(content)
    path.chmod(0o600)
    if os.name == 'nt':
        account = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip('\\')
        process = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'{account}:(F)'], capture_output=True)
        if process.returncode:
            raise RuntimeError('Não foi possível restringir a permissão do arquivo privado ao usuário atual.')


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('A senha deve ter entre 12 e 1024 caracteres.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
    return {'algorithm': 'scrypt', 'n': 32768, 'r': 8, 'p': 1, 'salt': base64.b64encode(salt).decode(), 'hash': base64.b64encode(digest).decode()}


def verify_password(password, record):
    if not isinstance(password, str) or len(password) > 1024:
        return False
    try:
        salt = base64.b64decode(record['salt'], validate=True)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(digest, base64.b64decode(record['hash'], validate=True))
    except (ValueError, KeyError, TypeError):
        return False


class Auth:
    def __init__(self, settings, connect):
        self.settings = settings
        self.connect = connect
        self.failures = {}
        self.lock = threading.Lock()
        owner_path = settings.data_dir / 'owner.json'
        self.owner = json.loads(owner_path.read_text(encoding='utf-8')) if owner_path.is_file() else None

    @property
    def configured(self):
        return bool(self.owner)

    def ensure_schema(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS auth_sessions (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL)')

    def token(self, cookie_header):
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header or '')
            return cookie[COOKIE].value if COOKIE in cookie else ''
        except CookieError:
            return ''

    def authenticated(self, cookie_header):
        if not self.configured:
            return True
        token = self.token(cookie_header)
        if not token:
            return False
        with self.connect() as db:
            self.ensure_schema(db)
            db.execute('DELETE FROM auth_sessions WHERE expires<=?', (time.time(),))
            row = db.execute('SELECT expires FROM auth_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return bool(row)

    def status(self, cookie_header=''):
        return {'required': self.configured, 'authenticated': self.authenticated(cookie_header), 'configured': self.configured}

    def login(self, password, address):
        if not self.configured:
            raise ValueError('Configure a senha do proprietário pelo terminal.')
        current = time.time()
        with self.lock:
            attempts = [value for value in self.failures.get(address, []) if value > current - 300]
            if len(attempts) >= 5:
                return None, 429
            attempts.append(current)
            self.failures[address] = attempts
            if len(self.failures) > 2000:
                self.failures = {key: values for key, values in self.failures.items() if values[-1] > current - 300}
        if not verify_password(password, self.owner):
            return None, 401
        with self.lock:
            self.failures.pop(address, None)
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            self.ensure_schema(db)
            db.execute('DELETE FROM auth_sessions WHERE expires<=?', (current,))
            db.execute('INSERT INTO auth_sessions VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), current + self.settings.session_hours * 3600))
        return self.cookie(token), 200

    def cookie(self, token='', clear=False):
        age = 0 if clear else self.settings.session_hours * 3600
        secure = '; Secure' if self.settings.secure_cookie else ''
        return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={age}{secure}'

    def logout(self, cookie_header):
        token = self.token(cookie_header)
        with self.connect() as db:
            self.ensure_schema(db)
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        return self.cookie(clear=True)


def setup():
    parser = argparse.ArgumentParser(description='Configurar senha do proprietário ORBIT')
    parser.parse_args()
    settings = config.Settings.from_env()
    path = settings.data_dir / 'owner.json'
    if path.exists():
        raise SystemExit('Senha já configurada. Preserve o arquivo existente. Para recuperação, faça backup e remova owner.json manualmente com o servidor parado.')
    password = getpass.getpass('Senha do proprietário (mínimo 12 caracteres): ')
    if password != getpass.getpass('Confirme a senha: '):
        raise SystemExit('As senhas não coincidem.')
    private_write(path, json.dumps(password_hash(password)))
    print('Senha configurada. Reinicie o servidor para ativar a autenticação.')


if __name__ == '__main__':
    setup()
