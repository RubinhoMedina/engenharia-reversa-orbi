"""Local pilot API. Run with python server/app.py. No external services."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import argparse
import json
import math
import mimetypes
import sqlite3
import subprocess
import uuid
from urllib.parse import unquote, parse_qs
import hashlib
import secrets
import os
import time
from http.cookies import SimpleCookie
import media
import config
import auth
import push
import importlib

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = config.Settings.from_env()
DATABASE = Path(os.getenv('ORBIT_DATABASE_PATH') or ROOT / 'server' / 'orbit.sqlite3').resolve()
MAX_BODY = 2 * 1024 * 1024
AUTH = None
PUSH = None


def runtime():
    global AUTH, PUSH
    if AUTH is None:
        AUTH = auth.Auth(SETTINGS, connect)
    if PUSH is None:
        PUSH = push.Push(SETTINGS, connect)
    return AUTH, PUSH


def integration_status():
    owner, notifications = runtime()
    result = {'config': SETTINGS.safe_status(), 'auth': {'configured': owner.configured, 'required': owner.configured}, 'push': notifications.status()}
    for name in ['ai', 'commerce']:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            result[name] = {'configured': False, 'detail': 'Módulo indisponível.'}
        else:
            result[name] = module.status()
    return result


def verify_binding(host):
    owner, _ = runtime()
    if SETTINGS.public_url or host not in {'127.0.0.1', 'localhost', '::1'}:
        if not owner.configured or not SETTINGS.public_url.startswith('https://'):
            raise ValueError('Acesso de rede exige senha do proprietário configurada e PUBLIC_URL HTTPS.')


def scan_imports():
    def importer(items):
        with connect() as db:
            return import_orders(db, items, 'manual')
    commerce = importlib.import_module('commerce')
    try:
        return commerce.scan_imports(importer)
    except Exception:
        commerce.set_setting('import_status', {'received': 0, 'changed': 0, 'files': 0, 'errors': [{'file': '', 'error': 'Não foi possível verificar a pasta de importação. Confira o caminho, as permissões e os arquivos.'}], 'timestamp': time.time()})
        raise RuntimeError('Falha ao verificar a pasta de importação. Confira a configuração e tente novamente.') from None


def now():
    return datetime.now(timezone.utc).isoformat()


def client_date():
    try:
        zone = ZoneInfo('America/Sao_Paulo')
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=-3))
    return datetime.now(zone).date().isoformat()


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE, timeout=15, factory=Connection)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id))')
    return db


def records(db, kind):
    return [json.loads(row[0]) for row in db.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid DESC', (kind,))]


def save(db, kind, value, record_id=None):
    value = dict(value)
    value['id'] = record_id or value.get('id') or str(uuid.uuid4())
    value['updated_at'] = now()
    db.execute('INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body', (kind, value['id'], json.dumps(value, ensure_ascii=False)))
    return value


def number(value, field, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f'{field} deve ser um número.')
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{field} deve ser um número.')
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f'{field} fora do intervalo permitido.')
    return result


def normalize_order(item, source):
    if not isinstance(item, dict):
        raise ValueError('Cada pedido deve ser um objeto.')
    order_id = str(item.get('id') or '').strip()
    product = str(item.get('product') or '').strip()
    account = str(item.get('account') or 'Principal').strip()
    parent_id = str(item.get('order_id') or '').strip()
    if not order_id or not product or not account or len(order_id) > 200 or len(parent_id) > 200 or len(account) > 100:
        raise ValueError('Informe id, product e uma conta válida. Identificadores têm limite de 200 caracteres.')
    quantity = number(item.get('quantity', 1), 'quantity', 1)
    if not quantity.is_integer():
        raise ValueError('quantity deve ser inteira.')
    date = str(item.get('date') or client_date())
    try:
        datetime.fromisoformat(date.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('date deve usar formato ISO 8601.')
    status = str(item.get('status', 'pago')).lower()
    commission_status = str(item.get('commission_status', 'estimada')).lower()
    if status not in {'pago', 'pendente', 'cancelado', 'reembolsado'}:
        raise ValueError('status inválido.')
    if commission_status not in {'estimada', 'aprovada', 'liquidada'}:
        raise ValueError('commission_status inválido.')
    order = dict(id=order_id, product=product[:500], account=account, gmv=number(item.get('gmv'), 'gmv'), commission=number(item.get('commission', 0), 'commission'), quantity=int(quantity), date=date, status=status, commission_status=commission_status, source=source, currency='BRL')
    if parent_id:
        order['order_id'] = parent_id
    return order


def import_orders(db, items, source='manual'):
    if not isinstance(items, list) or not items or len(items) > 5000:
        raise ValueError('Envie entre 1 e 5000 pedidos.')
    normalized = [normalize_order(item, source) for item in items]
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    changed = 0
    for order, original in zip(normalized, items):
        key = f"{source}:{order['account']}:{order['id']}"
        existing = db.execute('SELECT body FROM records WHERE kind=? AND id=?', ('orders', key)).fetchone()
        previous = json.loads(existing[0]) if existing else None
        if previous and not original.get('date'):
            order['date'] = previous['date']
        if previous and not order.get('order_id') and previous.get('order_id'):
            order['order_id'] = previous['order_id']
        candidate = dict(order, id=key, source_id=order['id'])
        if previous and all(previous.get(k) == v for k, v in candidate.items()):
            continue
        save(db, 'orders', candidate, key)
        save(db, 'notifications', {'title': 'Atualização demonstrativa' if source == 'demo' else 'Importação atualizada', 'message': f"{order['product']} · comissão R$ {order['commission']:.2f}", 'source': source, 'created_at': now(), 'order_id': key})
        changed += 1
    return {'received': len(items), 'changed': changed, 'unchanged': len(items) - changed}


def analyze(payload):
    transcript = str(payload.get('transcript', '')).strip()
    if not transcript or len(transcript) > 100000:
        raise ValueError('Informe uma transcrição de até 100 mil caracteres.')
    duration = number(payload.get('duration', 60), 'duration', 1)
    if duration > 600:
        raise ValueError('A duração máxima do piloto é 10 minutos.')
    text = transcript.lower()
    checks = [
        ('Gancho', len(transcript.split()) >= 8, 'Abra com o problema concreto do público e apresente a proposta nos primeiros segundos.'),
        ('Desenvolvimento', len(transcript.split()) >= 45, 'Organize problema, benefício comprovado e demonstração em uma sequência curta.'),
        ('Storytelling', any(word in text for word in ['antes', 'depois', 'quando', 'eu ', 'minha']), 'Inclua uma situação real, o que mudou e o resultado observável, sem prometer resultados.'),
        ('Demonstração e prova', any(word in text for word in ['mostr', 'veja', 'teste', 'demonstr']), 'Mostre o uso e o detalhe do produto que sustenta o benefício informado.'),
        ('CTA', any(word in text for word in ['confira', 'clique', 'acesse', 'veja', 'comente', 'salve']), 'Finalize com uma ação clara e adequada ao objetivo do vídeo.'),
    ]
    dimensions = [{'name': name, 'status': 'indício textual' if found else 'revisar', 'reason': 'A transcrição contém um padrão relacionado ao critério.' if found else 'O padrão esperado não foi identificado na transcrição.', 'suggestion': suggestion, 'timestamp': None} for name, found, suggestion in checks]
    return {'transcript': transcript, 'duration': duration, 'filename': str(payload.get('filename', 'Transcrição manual'))[:250], 'method': 'Regras textuais locais v1', 'limitations': 'Avaliação heurística da transcrição fornecida. Imagem, entonação e ritmo de edição não foram analisados. Tempos do roteiro são sugestões.', 'dimensions': dimensions, 'hook': 'Você também enfrenta este problema? Veja como eu uso este produto.', 'revised_script': 'Abertura — apresente um problema real.\nDemonstração — mostre o produto em uso e apenas benefícios comprovados.\nContexto — conte sua experiência verificável.\nCTA — convide a conferir os detalhes antes de decidir.', 'created_at': now()}


def dispatch(db, path, payload):
    if path == '/api/orders/import':
        if 'csv' in payload:
            if 'orders' in payload or not isinstance(payload['csv'], str):
                raise ValueError('Envie apenas um arquivo CSV ou uma lista de pedidos.')
            items = importlib.import_module('commerce').parse_import(payload['csv'].encode('utf-8'), '.csv')
        else:
            items = payload.get('orders')
        return import_orders(db, items)
    if path == '/api/demo':
        today = client_date()
        sample = [dict(id=str(i), product=product, gmv=price, commission=round(price * .15, 2), status='pago', commission_status=status, date=today, account='Perfil demonstração', quantity=1) for i, (product, price, status) in enumerate([('Kit de organização', 129.90, 'estimada'), ('Garrafa térmica', 89.90, 'aprovada'), ('Luminária de mesa', 159.90, 'liquidada'), ('Kit de organização', 129.90, 'estimada')])]
        return import_orders(db, sample, 'demo')
    if path == '/api/scripts':
        if not str(payload.get('product', '')).strip():
            raise ValueError('Informe o produto.')
        return save(db, 'scripts', dict(payload, created_at=now(), method=payload.get('method') or 'Modelo editorial local v1'))
    if path == '/api/creators':
        handle = str(payload.get('handle', '')).strip()
        if not handle:
            raise ValueError('Informe o identificador do creator.')
        return save(db, 'creators', dict(payload, handle=handle, source='fornecido pelo usuário', created_at=now()))
    if path == '/api/analyses':
        return save(db, 'analyses', analyze(payload))
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        self.log_message('%s %s %s', self.command, urlparse(self.path).path, code)

    def oauth_binding(self):
        owner, _ = runtime()
        token = owner.token(self.headers.get('Cookie', '')) if owner.configured else ''
        if not owner.configured:
            try:
                cookies = SimpleCookie()
                cookies.load(self.headers.get('Cookie', ''))
                token = cookies['orbit_oauth'].value if 'orbit_oauth' in cookies else ''
            except auth.CookieError:
                token = ''
        return hashlib.sha256(token.encode()).hexdigest() if token else ''

    def allowed_origins(self):
        port = self.server.server_port
        values = {f'http://localhost:{port}', f'http://127.0.0.1:{port}', 'http://localhost:5173', 'http://127.0.0.1:5173'}
        if SETTINGS.public_origin:
            values.add(SETTINGS.public_origin)
        return values

    def valid_host(self):
        host = self.headers.get('Host', '')
        allowed = {urlparse(origin).netloc for origin in self.allowed_origins()}
        return host.lower() in {item.lower() for item in allowed}

    def valid_mutation(self):
        if not self.valid_host():
            return False
        origin = self.headers.get('Origin')
        if origin:
            return origin in self.allowed_origins()
        # Native clients can omit Origin. Browser mutation requests must be same-origin.
        return self.headers.get('Sec-Fetch-Site') in {None, 'same-origin', 'none'}

    def require_auth(self):
        owner, _ = runtime()
        if not owner.authenticated(self.headers.get('Cookie', '')):
            self.send_json({'error': 'Entre com a senha do proprietário.'}, 401)
            return False
        return True

    def send_json(self, value, status=200, cookie=None):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if status == 429:
            self.send_header('Retry-After', '300')
        origin = self.headers.get('Origin', '')
        if origin in self.allowed_origins():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if not self.valid_mutation():
            return self.send_json({'error': 'Origem ou Host não autorizado.'}, 403)
        self.send_response(204)
        origin = self.headers.get('Origin', '')
        if origin in self.allowed_origins():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Filename')
        self.end_headers()

    def do_GET(self):
        if not self.valid_host():
            return self.send_json({'error': 'Host não autorizado.'}, 403)
        path = urlparse(self.path).path
        if path == '/api/health':
            return self.send_json({'status': 'ok', 'mode': SETTINGS.safe_status()['mode']})
        if path == '/api/auth/status':
            return self.send_json(runtime()[0].status(self.headers.get('Cookie', '')))
        if path == '/api/commerce/tiktok/callback':
            query = parse_qs(urlparse(self.path).query)
            binding = self.oauth_binding()
            succeeded = False
            commerce = importlib.import_module('commerce')
            try:
                if not binding or not runtime()[0].authenticated(self.headers.get('Cookie', '')):
                    raise ValueError('Sessão OAuth ausente.')
                commerce.callback(query.get('code', [''])[0], query.get('state', [''])[0], binding)
                succeeded = True
            except (ValueError, RuntimeError, OSError, sqlite3.Error):
                pass
            try:
                commerce.set_setting('oauth_status', {'ok': succeeded, 'detail': 'Conta Creator autorizada. Confira a cobertura da conexão.' if succeeded else 'A autorização não foi concluída. Confira a configuração e inicie novamente.', 'timestamp': time.time()})
            except (sqlite3.Error, OSError):
                pass
            self.send_response(303)
            self.send_header('Location', '/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Orbit-OAuth-Result', 'connected' if succeeded else 'failed')
            self.end_headers()
            return
        if path.startswith('/api/') and not self.require_auth():
            return
        if path == '/api/push/config':
            return self.send_json(runtime()[1].status())
        if path == '/api/integrations':
            return self.send_json(integration_status())
        if path == '/api/state':
            with connect() as db:
                return self.send_json({kind: records(db, kind) for kind in ['orders', 'scripts', 'creators', 'analyses', 'notifications']})
        if path.startswith('/api/'):
            return self.send_json({'error': 'Rota desconhecida.'}, 404)
        base = (ROOT / 'dist').resolve()
        target = (base / path.lstrip('/')).resolve()
        if not target.is_relative_to(base):
            return self.send_json({'error': 'Caminho inválido.'}, 403)
        if not target.is_file():
            target = base / 'index.html'
        if not target.is_file():
            return self.send_json({'error': 'Frontend ainda não compilado. Execute npm run build.'}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(target)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.valid_mutation():
            return self.send_json({'error': 'Origem ou Host não autorizado.'}, 403)
        path = urlparse(self.path).path
        if path != '/api/auth/login' and not self.require_auth():
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if path == '/api/videos':
                filename = Path(unquote(self.headers.get('X-Filename', 'video.mp4'))).name
                result = media.receive_and_transcribe(self.rfile, size, filename, self.headers.get('Content-Type', '').split(';')[0])
                analysis_payload = dict(result, filename=filename)
                baseline = analyze(analysis_payload)
                try:
                    analysis = importlib.import_module('ai').enrich_analysis(analysis_payload, baseline)
                except (RuntimeError, ValueError):
                    analysis = {**baseline, 'analysis_notice': 'A IA estava indisponível ou retornou uma análise inválida. O Orbit salvou a transcrição e a avaliação local. Você pode revisar o texto e tentar novamente.'}
                analysis.update(segments=result['segments'], transcription_method='Faster Whisper tiny CPU int8', processing_seconds=result['processing_seconds'], has_video=result['has_video'])
                if 'visual' in result:
                    analysis['visual'] = result['visual']
                with connect() as db:
                    analysis = save(db, 'analyses', analysis)
                return self.send_json({'analysis': analysis, 'transcript': result['transcript']})
            if not 0 < size <= MAX_BODY:
                raise ValueError('Corpo da requisição excede 2 MB ou está vazio.')
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Use Content-Type application/json.')
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError('Envie um objeto JSON.')
            owner, notifications = runtime()
            if path == '/api/auth/login':
                cookie, status = owner.login(payload.get('password'), self.client_address[0])
                return self.send_json({'authenticated': status == 200, **({'error': 'Aguarde cinco minutos antes de tentar novamente.' if status == 429 else 'Senha inválida.'} if status != 200 else {})}, status, cookie)
            if path == '/api/auth/logout':
                return self.send_json({'authenticated': False}, cookie=owner.logout(self.headers.get('Cookie', '')))
            if path == '/api/push/subscribe':
                return self.send_json(notifications.subscribe(payload.get('subscription')))
            if path == '/api/push/unsubscribe':
                return self.send_json(notifications.unsubscribe(payload.get('endpoint')))
            if path == '/api/push/test':
                return self.send_json(notifications.enqueue_test())
            if path == '/api/ai/generate':
                return self.send_json(importlib.import_module('ai').generate(payload))
            if path == '/api/ai/test':
                return self.send_json(importlib.import_module('ai').test_connection())
            if path == '/api/commerce/tiktok/start':
                binding = self.oauth_binding()
                oauth_cookie = None
                if not owner.configured:
                    token = secrets.token_urlsafe(32)
                    binding = hashlib.sha256(token.encode()).hexdigest()
                    secure = '; Secure' if SETTINGS.secure_cookie else ''
                    oauth_cookie = f'orbit_oauth={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600{secure}'
                return self.send_json(importlib.import_module('commerce').start_authorization(binding), cookie=oauth_cookie)
            if path == '/api/commerce/tiktok/refresh':
                return self.send_json(importlib.import_module('commerce').refresh_tokens())
            if path == '/api/commerce/tiktok/disconnect':
                return self.send_json(importlib.import_module('commerce').disconnect())
            if path == '/api/commerce/imports/scan':
                result = scan_imports()
                notifications.wake_event.set()
                return self.send_json(result)
            if path == '/api/analyses':
                baseline = analyze(payload)
                result = baseline if payload.get('engine') == 'rules' else importlib.import_module('ai').enrich_analysis(payload, baseline)
                with connect() as db:
                    result = save(db, 'analyses', result)
                return self.send_json(result)
            with connect() as db:
                result = dispatch(db, path, payload)
            notifications.wake_event.set()
            self.send_json(result)
        except (ValueError, TypeError) as error:
            self.send_json({'error': str(error)}, 400)
        except KeyError:
            self.send_json({'error': 'Rota desconhecida.'}, 404)
        except sqlite3.Error:
            self.send_json({'error': 'Falha de persistência. Tente novamente.'}, 503)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
            self.send_json({'error': f'Processamento local indisponível. {error}'}, 503)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    verify_binding(args.host)
    connect().close()
    runtime()[1].background_task = scan_imports
    runtime()[1].background_interval = config.integer('ORBIT_IMPORT_INTERVAL_SECONDS', 60, 30, 86400)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    runtime()[1].start()
    print(f'ORBIT em http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        runtime()[1].stop()
        server.server_close()
