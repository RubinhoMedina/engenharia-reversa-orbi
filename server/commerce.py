"""Creator OAuth and automatic ingestion of owner-provided JSON/CSV exports."""
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('ORBIT_DATA_DIR') or ROOT / 'server' / 'data')
STORE = DATA / 'commerce.sqlite3'
TOKEN_LOCK = threading.Lock()
SCAN_LOCK = threading.Lock()
CSV_COLUMNS = ('id', 'product', 'gmv', 'commission', 'status', 'date', 'account', 'quantity', 'commission_status')
MAX_IMPORT_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(STORE, timeout=15)
    db.execute('CREATE TABLE IF NOT EXISTS state (digest TEXT PRIMARY KEY, session TEXT, expires REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return db


def get_setting(key, default=None):
    db = connect()
    try:
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default
    finally:
        db.close()


def set_setting(key, value):
    db = connect()
    try:
        with db:
            db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (key, json.dumps(value)))
    finally:
        db.close()


def scopes_required():
    return {s.strip() for s in os.getenv('TIKTOK_REQUIRED_SCOPES', '').split(',') if s.strip()}


def status():
    configured = bool(os.getenv('TIKTOK_APP_KEY') and os.getenv('TIKTOK_APP_SECRET') and
                      os.getenv('TIKTOK_REDIRECT_URI') and scopes_required())
    profile = get_setting('profile', {})
    folder = os.getenv('ORBIT_IMPORT_DIRECTORY', '')
    return {'configured': configured, 'connected': bool(profile and get_setting('encrypted_tokens')), 'granted_scopes': profile.get('granted_scopes', []),
            'identity': profile.get('open_id_suffix'), 'expires_at': profile.get('expires_at'),
            'token_expired': bool(profile and profile.get('expires_at', 0) <= time.time()),
            'sales_api_ready': False,
            'oauth_status': get_setting('oauth_status', {}),
            'detail': 'OAuth de creator preparado. Pedidos oficiais exigem confirmar endpoint, contrato e acesso BR no aplicativo aprovado.',
            'imports': {'configured': bool(folder), 'directory_exists': bool(folder and Path(folder).is_dir()),
                        'formats': ['json', 'csv'], 'csv_columns': list(CSV_COLUMNS),
                        'sources': get_setting('import_sources', {}),
                        'last_run': get_setting('import_status', {})}}


def start_authorization(session):
    if not status()['configured']:
        raise ValueError('Configure App Key, App Secret, Redirect URI e os escopos aprovados no Partner Center.')
    redirect = urlparse(os.environ['TIKTOK_REDIRECT_URI'])
    if redirect.path != '/api/commerce/tiktok/callback' or redirect.scheme not in {'https', 'http'}:
        raise ValueError('O Redirect URI deve apontar para /api/commerce/tiktok/callback.')
    if redirect.scheme == 'http' and redirect.hostname not in {'localhost', '127.0.0.1'}:
        raise ValueError('O callback publicado deve usar HTTPS.')
    state = secrets.token_urlsafe(32)
    db = connect()
    try:
        with db:
            db.execute('DELETE FROM state WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO state VALUES(?,?,?)', (hashlib.sha256(state.encode()).hexdigest(), session, time.time() + 600))
    finally:
        db.close()
    return {'authorize_url': 'https://shop.tiktok.com/alliance/creator/auth?' + urlencode({'app_key': os.environ['TIKTOK_APP_KEY'], 'state': state})}


def cipher():
    from cryptography.fernet import Fernet
    DATA.mkdir(parents=True, exist_ok=True)
    key_path = DATA / 'token-vault.key'
    from auth import private_write
    if not key_path.exists():
        private_write(key_path, Fernet.generate_key().decode())
    return Fernet(key_path.read_bytes())


def exchange(endpoint, parameters):
    parameters.update(app_key=os.environ['TIKTOK_APP_KEY'], app_secret=os.environ['TIKTOK_APP_SECRET'])
    request = Request('https://auth.tiktok-shops.com/api/v2/token/' + endpoint + '?' + urlencode(parameters))
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            body = response.read(512 * 1024)
        result = json.loads(body)
    except (HTTPError, URLError, ValueError, TimeoutError):
        raise RuntimeError('Não foi possível obter autorização TikTok. Confira o aplicativo e refaça a autorização.') from None
    if type(result.get('code')) is not int or result['code'] != 0 or not isinstance(result.get('data'), dict):
        raise ValueError('TikTok recusou a autorização. Verifique as permissões do aplicativo.')
    data = result['data']
    granted = data.get('granted_scopes', [])
    if not isinstance(granted, list) or any(not isinstance(scope, str) for scope in granted) or type(data.get('user_type')) is not int or data['user_type'] != 1 or not scopes_required().issubset(set(granted)):
        raise ValueError('A autorização precisa ser de Creator e incluir todos os escopos configurados.')
    if not data.get('access_token') or not data.get('refresh_token') or not data.get('open_id'):
        raise ValueError('TikTok retornou credenciais incompletas.')
    return data


def store_tokens(data):
    expiry = float(data.get('access_token_expire_in', 0))
    if not math.isfinite(expiry) or expiry <= 0:
        raise ValueError('TikTok retornou validade de token ausente ou inválida.')
    expiry = expiry if expiry > 1000000000 else time.time() + expiry
    envelope = cipher().encrypt(json.dumps(data).encode()).decode()
    profile = {'open_id_suffix': str(data['open_id'])[-6:], 'granted_scopes': data['granted_scopes'], 'expires_at': expiry}
    db = connect()
    try:
        with db:
            db.executemany('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           [('encrypted_tokens', json.dumps(envelope)), ('profile', json.dumps(profile))])
    finally:
        db.close()


def callback(code, state, session):
    if not code or not state or len(code) > 4096 or len(state) > 256:
        raise ValueError('Callback OAuth incompleto.')
    digest = hashlib.sha256(state.encode()).hexdigest()
    db = connect()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT session,expires FROM state WHERE digest=?', (digest,)).fetchone()
            if not row or row[1] < time.time() or not secrets.compare_digest(row[0], session):
                raise ValueError('Autorização expirada ou sessão inválida. Inicie novamente.')
            db.execute('DELETE FROM state WHERE digest=?', (digest,))
    finally:
        db.close()
    with TOKEN_LOCK:
        data = exchange('get', {'auth_code': code, 'grant_type': 'authorized_code'})
        store_tokens(data)
    return {'connected': True, 'detail': 'Creator autorizado. Leitura de pedidos ainda depende do contrato da API aprovado.'}


def refresh_tokens():
    with TOKEN_LOCK:
        envelope = get_setting('encrypted_tokens')
        if not envelope:
            raise ValueError('Nenhuma conta Creator autorizada.')
        old = json.loads(cipher().decrypt(envelope.encode()))
        data = exchange('refresh', {'refresh_token': old['refresh_token'], 'grant_type': 'refresh_token'})
        if data['open_id'] != old['open_id']:
            raise ValueError('A identidade do Creator mudou. Refaça a conexão.')
        store_tokens(data)
    return {'refreshed': True}


def disconnect():
    db = connect()
    try:
        with db:
            db.execute("DELETE FROM settings WHERE key IN ('profile','encrypted_tokens')")
            db.execute('DELETE FROM state')
    finally:
        db.close()
    return {'connected': False, 'detail': 'Credenciais locais removidas. Revogue também no TikTok para remover a concessão na origem.'}


def scan_imports(importer):
    with SCAN_LOCK:
        return scan_directory(importer)


def csv_money(value, field, row):
    text = value.strip()
    if not re.fullmatch(r'\d+(?:[.,]\d{1,2})?', text):
        raise ValueError(f'Linha {row}: {field} deve ser um valor positivo com até duas casas decimais, sem separador de milhar.')
    try:
        amount = Decimal(text.replace(',', '.'))
    except InvalidOperation:
        raise ValueError(f'Linha {row}: {field} inválido.') from None
    if not amount.is_finite() or amount > Decimal('1000000000000'):
        raise ValueError(f'Linha {row}: {field} fora do limite permitido.')
    return float(amount)


def parse_csv_orders(content):
    """Parse the explicit ORBIT interchange format, without guessing TikTok exports."""
    if len(content) > MAX_IMPORT_BYTES:
        raise ValueError('O CSV excede 2 MB.')
    try:
        text = content.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Salve o CSV em UTF-8.') from None
    if '\x00' in text:
        raise ValueError('O CSV contém caracteres inválidos.')
    first_line = text.splitlines()[0] if text.splitlines() else ''
    separator = ';' if ';' in first_line else ','
    reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=separator, strict=True)
    try:
        headers = reader.fieldnames
    except csv.Error:
        raise ValueError('Cabeçalho CSV malformado.') from None
    allowed = set(CSV_COLUMNS) | {'currency', 'order_id'}
    if not headers or len(set(headers)) != len(headers) or set(CSV_COLUMNS) - set(headers) or set(headers) - allowed:
        raise ValueError('Cabeçalhos CSV inválidos. Use id,product,gmv,commission,status,date,account,quantity,commission_status. currency e order_id são opcionais.')
    orders = []
    identifiers = set()
    try:
        for row, values in enumerate(reader, start=2):
            if row > 5001:
                raise ValueError('O CSV deve conter até 5000 registros.')
            if None in values or any(value is None for value in values.values()):
                raise ValueError(f'Linha {row}: quantidade de campos diferente do cabeçalho.')
            values = {key: value.strip() for key, value in values.items()}
            if any(not values[key] for key in CSV_COLUMNS):
                raise ValueError(f'Linha {row}: preencha todos os campos obrigatórios.')
            if any(any(ord(character) < 32 for character in value) for value in values.values()):
                raise ValueError(f'Linha {row}: caracteres de controle não são permitidos.')
            if len(values['id']) > 200 or len(values['product']) > 500 or len(values['account']) > 100:
                raise ValueError(f'Linha {row}: identificador, produto ou perfil excede o limite.')
            if len(values.get('order_id', '')) > 200:
                raise ValueError(f'Linha {row}: order_id excede o limite.')
            if values.get('currency', 'BRL') != 'BRL':
                raise ValueError(f'Linha {row}: este importador aceita somente BRL.')
            if values['status'] not in {'pago', 'pendente', 'cancelado', 'reembolsado'}:
                raise ValueError(f'Linha {row}: status deve ser pago, pendente, cancelado ou reembolsado.')
            if values['commission_status'] not in {'estimada', 'aprovada', 'liquidada'}:
                raise ValueError(f'Linha {row}: commission_status inválido.')
            if not re.fullmatch(r'[1-9]\d{0,5}', values['quantity']):
                raise ValueError(f'Linha {row}: quantity deve ser inteira entre 1 e 999999.')
            from datetime import datetime
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.+)?', values['date']):
                    raise ValueError()
                parsed_date = datetime.fromisoformat(values['date'].replace('Z', '+00:00'))
                if 'T' in values['date'] and parsed_date.tzinfo is None:
                    raise ValueError()
            except ValueError:
                raise ValueError(f'Linha {row}: date deve usar AAAA-MM-DD ou ISO 8601 com fuso horário.') from None
            identifier = (values['account'], values['id'])
            if identifier in identifiers:
                raise ValueError(f'Linha {row}: id repetido no mesmo perfil. Use id único por item ou um único estado atualizado.')
            identifiers.add(identifier)
            orders.append({**values, 'quantity': int(values['quantity']), 'gmv': csv_money(values['gmv'], 'gmv', row), 'commission': csv_money(values['commission'], 'commission', row)})
    except csv.Error:
        raise ValueError('CSV malformado. Confira aspas e separadores.') from None
    if not orders:
        raise ValueError('O CSV está vazio.')
    return orders


def parse_import(content, suffix):
    if not isinstance(content, bytes) or len(content) > MAX_IMPORT_BYTES:
        raise ValueError('Envie um arquivo de até 2 MB.')
    if not isinstance(suffix, str):
        raise ValueError('Informe o formato json ou csv.')
    kind = suffix.lower().lstrip('.')
    if kind == 'csv':
        return parse_csv_orders(content)
    if kind != 'json':
        raise ValueError('Formato de importação deve ser JSON ou CSV.')
    try:
        value = json.loads(content)
        items = value if isinstance(value, list) else value.get('orders') if isinstance(value, dict) else None
    except (ValueError, UnicodeError):
        raise ValueError('JSON inválido. Confira o arquivo fornecido.') from None
    if not isinstance(items, list) or not 1 <= len(items) <= 5000:
        raise ValueError('O JSON deve conter entre 1 e 5000 pedidos.')
    return items


def scan_directory(importer):
    """Owner-selected folder contains canonical export files, never executable jobs."""
    folder = os.getenv('ORBIT_IMPORT_DIRECTORY', '')
    if not folder:
        return {'configured': False}
    directory = Path(folder).resolve()
    if not directory.is_dir():
        raise ValueError('A pasta de importação configurada não existe.')
    fingerprints = get_setting('import_fingerprints', {})
    sources = get_setting('import_sources', {})
    report = {'received': 0, 'changed': 0, 'files': 0, 'errors': [], 'sources': [], 'timestamp': time.time()}
    paths = sorted(path for path in directory.iterdir() if path.suffix.lower() in {'.json', '.csv'})[:100]
    for path in paths:
        try:
            if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
                continue
            before = path.stat()
            if before.st_size > MAX_IMPORT_BYTES:
                raise ValueError('O arquivo excede 2 MB.')
            if time.time() - before.st_mtime < 2:
                continue
            with path.open('rb') as source:
                content = source.read(MAX_IMPORT_BYTES + 1)
            after = path.stat()
            if len(content) > MAX_IMPORT_BYTES:
                raise ValueError('O arquivo excede 2 MB.')
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                continue
            digest = hashlib.sha256(content).hexdigest()
            if fingerprints.get(path.name) == digest:
                continue
            items = parse_import(content, path.suffix)
            result = importer(items)
            report['files'] += 1
            report['received'] += result['received']
            report['changed'] += result['changed']
            report['sources'].append({'file': path.name, 'format': path.suffix.lower().lstrip('.'), 'sha256': digest, 'records': result['received'], 'source': 'manual'})
            sources[path.name] = {**report['sources'][-1], 'imported_at': time.time()}
            fingerprints[path.name] = digest
        except (ValueError, AttributeError, TypeError, OSError) as error:
            detail = str(error) if path.suffix.lower() == '.csv' and isinstance(error, ValueError) else 'Arquivo inválido. Confira o formato de pedidos documentado.'
            report['errors'].append({'file': path.name, 'error': detail})
    set_setting('import_sources', sources)
    set_setting('import_fingerprints', fingerprints)
    set_setting('import_status', report)
    return report
