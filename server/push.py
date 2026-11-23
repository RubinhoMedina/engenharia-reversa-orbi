"""Encrypted subscriptions and durable per-device Web Push delivery ledger."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
import uuid
from datetime import datetime
import config
from auth import private_write


def encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def decode(value):
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError('Chave de inscrição inválida.')
    try:
        return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    except (ValueError, TypeError):
        raise ValueError('Chave de inscrição inválida.')


def validate_endpoint(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 4096 or any(ord(char) < 33 for char in endpoint):
        raise ValueError('Endpoint de push inválido.')
    parsed = urlparse(endpoint)
    try:
        valid_port = parsed.port in {None, 443}
    except ValueError:
        valid_port = False
    hostname = parsed.hostname or ''
    permitted = hostname in {'fcm.googleapis.com', 'web.push.apple.com', 'updates.push.services.mozilla.com'} or hostname.endswith('.push.services.mozilla.com')
    if parsed.scheme != 'https' or not permitted or not valid_port or parsed.username or parsed.password or parsed.fragment or not parsed.path:
        raise ValueError('Use uma inscrição HTTPS de FCM, Mozilla Push ou Apple Push.')
    return endpoint


def validate_subscription(subscription):
    if not isinstance(subscription, dict):
        raise ValueError('Inscrição inválida.')
    endpoint = validate_endpoint(subscription.get('endpoint'))
    keys = subscription.get('keys')
    if not isinstance(keys, dict):
        raise ValueError('Inscrição sem chaves.')
    auth_key = decode(keys.get('auth'))
    public = decode(keys.get('p256dh'))
    if len(auth_key) != 16 or len(public) != 65 or public[0] != 4:
        raise ValueError('Chaves de inscrição inválidas.')
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    except ValueError:
        raise ValueError('Chave pública de inscrição inválida.')
    return {'endpoint': endpoint, 'keys': {'auth': keys['auth'], 'p256dh': keys['p256dh']}}


def ensure_schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS push_subscriptions (device TEXT PRIMARY KEY, encrypted TEXT NOT NULL, created REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS push_deliveries (event TEXT, device TEXT, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT \'pending\', attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0, error TEXT, PRIMARY KEY(event,device))')


class Push:
    def __init__(self, settings, connect, sender=None):
        self.settings = settings
        self.connect = connect
        self.sender = sender
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        self.background_task = None
        self.background_interval = 60
        self.last_background_run = 0
        self.files = settings.data_dir / 'push'
        self.public_key = ''
        self.subject = settings.push_subject
        self.cipher = None
        info = self.files / 'vapid.json'
        if info.is_file() and importlib.util.find_spec('cryptography'):
            from cryptography.fernet import Fernet
            metadata = json.loads(info.read_text(encoding='utf-8'))
            self.public_key = metadata['public_key']
            self.subject = self.subject or metadata['subject']
            self.cipher = Fernet((self.files / 'subscriptions.key').read_bytes())

    @property
    def configured(self):
        return bool(self.public_key and self.subject and self.cipher and (self.files / 'private.pem').is_file() and (self.sender or importlib.util.find_spec('pywebpush')))

    def status(self):
        with self.connect() as db:
            ensure_schema(db)
            devices = db.execute('SELECT COUNT(*) FROM push_subscriptions').fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM push_deliveries WHERE status IN ('pending','sending')").fetchone()[0]
            delivery_counts = dict(db.execute('SELECT status,COUNT(*) FROM push_deliveries GROUP BY status').fetchall())
        return {'configured': self.configured, 'public_key': self.public_key if self.configured else '', 'devices': devices, 'pending': pending, 'deliveries': delivery_counts, 'worker_running': bool(self.thread and self.thread.is_alive())}

    def subscribe(self, subscription):
        if not self.configured:
            raise ValueError('Configure as chaves VAPID pelo terminal primeiro.')
        subscription = validate_subscription(subscription)
        device = hashlib.sha256(subscription['endpoint'].encode()).hexdigest()
        encrypted = self.cipher.encrypt(json.dumps(subscription).encode()).decode()
        with self.connect() as db:
            ensure_schema(db)
            db.execute('INSERT INTO push_subscriptions VALUES(?,?,?) ON CONFLICT(device) DO UPDATE SET encrypted=excluded.encrypted', (device, encrypted, time.time()))
        return {'subscribed': True, 'device': device}

    def unsubscribe(self, endpoint):
        endpoint = validate_endpoint(endpoint)
        device = hashlib.sha256(endpoint.encode()).hexdigest()
        with self.connect() as db:
            ensure_schema(db)
            db.execute('DELETE FROM push_subscriptions WHERE device=?', (device,))
            db.execute("UPDATE push_deliveries SET status='unsubscribed' WHERE device=? AND status IN ('pending','sending')", (device,))
        return {'subscribed': False}

    def enqueue_test(self):
        if not self.configured:
            raise ValueError('Web Push ainda não foi configurado.')
        event = f'test:{uuid.uuid4()}'
        with self.connect() as db:
            ensure_schema(db)
            devices = db.execute('SELECT device FROM push_subscriptions').fetchall()
            if not devices:
                raise ValueError('Inscreva este dispositivo antes de enviar um teste.')
            payload = json.dumps({'title': 'ORBIT · notificação de teste', 'body': 'O Web Push está funcionando neste dispositivo.', 'tag': event, 'url': '/', 'test': True})
            for (device,) in devices:
                db.execute('INSERT OR IGNORE INTO push_deliveries(event,device,payload) VALUES(?,?,?)', (event, device, payload))
        self.wake_event.set()
        return {'queued': len(devices), 'test': True}

    def enqueue_notifications(self):
        with self.connect() as db:
            ensure_schema(db)
            devices = db.execute('SELECT device,created FROM push_subscriptions').fetchall()
            if not devices:
                return
            events = db.execute("SELECT id,body FROM records WHERE kind='notifications'").fetchall()
            for event, body in events:
                notification = json.loads(body)
                try:
                    created = datetime.fromisoformat(notification.get('created_at', '').replace('Z', '+00:00')).timestamp()
                except ValueError:
                    continue
                source = notification.get('source', '')
                test = source not in {'tiktok', 'tiktok_authorized'}
                payload = json.dumps({'title': 'ORBIT · teste de atualização' if test else 'ORBIT · dados atualizados', 'body': 'Demonstração ou importação atualizada. Abra o app para conferir.' if test else 'Uma atualização comercial foi identificada. Abra o app para conferir a origem e o horário.', 'tag': f'event:{event}', 'url': '/', 'test': test})
                for device, subscribed in devices:
                    if created >= subscribed:
                        db.execute('INSERT OR IGNORE INTO push_deliveries(event,device,payload) VALUES(?,?,?)', (event, device, payload))

    def send(self, subscription, payload):
        if self.sender:
            return self.sender(subscription, payload)
        from pywebpush import webpush
        from requests import Session
        class PushSession(Session):
            def request(self, method, url, **kwargs):
                kwargs['allow_redirects'] = False
                return super().request(method, url, **kwargs)
        with PushSession() as session:
            return webpush(subscription_info=subscription, data=payload, vapid_private_key=str(self.files / 'private.pem'), vapid_claims={'sub': self.subject}, ttl=300, timeout=15, requests_session=session)

    def deliver_pending(self):
        if not self.configured:
            return
        for _ in range(50):
            if self.stop_event.is_set():
                return
            current = time.time()
            with self.connect() as db:
                ensure_schema(db)
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT d.event,d.device,d.payload,d.attempts,s.encrypted FROM push_deliveries d JOIN push_subscriptions s ON s.device=d.device WHERE (d.status='pending' AND d.next_attempt<=?) OR (d.status='sending' AND d.lease_until<=?) ORDER BY d.next_attempt LIMIT 1", (current, current)).fetchone()
                if not row:
                    return
                event, device, payload, attempts, encrypted = row
                db.execute("UPDATE push_deliveries SET status='sending',attempts=attempts+1,lease_until=? WHERE event=? AND device=?", (current + 90, event, device))
            try:
                subscription = json.loads(self.cipher.decrypt(encrypted.encode()))
                validate_subscription(subscription)
                self.send(subscription, payload)
            except Exception as error:
                response = getattr(error, 'response', None)
                status_code = getattr(response, 'status_code', None)
                with self.connect() as db:
                    if status_code in {404, 410}:
                        db.execute('DELETE FROM push_subscriptions WHERE device=?', (device,))
                        db.execute("UPDATE push_deliveries SET status='expired',error='endpoint_expired' WHERE device=? AND status IN ('sending','pending')", (device,))
                    else:
                        retry = attempts + 1 < 6 and (status_code is None or status_code == 429 or status_code >= 500)
                        db.execute('UPDATE push_deliveries SET status=?,next_attempt=?,error=? WHERE event=? AND device=?', ('pending' if retry else 'failed', current + min(3600, 30 * 2 ** attempts), f'push_http_{status_code}' if status_code else 'push_delivery_error', event, device))
            else:
                with self.connect() as db:
                    db.execute("UPDATE push_deliveries SET status='sent',error=NULL WHERE event=? AND device=?", (event, device))

    def run_once(self):
        if self.stop_event.is_set():
            return
        if self.background_task and time.monotonic() - self.last_background_run >= self.background_interval:
            self.last_background_run = time.monotonic()
            try:
                self.background_task()
            except Exception:
                pass
        if self.configured:
            self.enqueue_notifications()
            self.deliver_pending()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        def work():
            while not self.stop_event.is_set():
                try:
                    self.run_once()
                except Exception:
                    # Do not log endpoints, keys or provider error bodies.
                    pass
                self.wake_event.wait(self.settings.push_interval)
                self.wake_event.clear()
        self.thread = threading.Thread(target=work, name='orbit-push', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=20)


def setup():
    parser = argparse.ArgumentParser(description='Gerar chaves VAPID e chave de armazenamento privado')
    parser.add_argument('--subject', required=True, help='Contato mailto: ou URL HTTPS do responsável')
    args = parser.parse_args()
    subject = args.subject
    if not ((subject.startswith('mailto:') and '@' in subject) or (subject.startswith('https://') and urlparse(subject).hostname)):
        raise SystemExit('Informe contato mailto: ou URL HTTPS válido.')
    settings = config.Settings.from_env()
    folder = settings.data_dir / 'push'
    if folder.exists() and any(folder.iterdir()):
        raise SystemExit('Chaves existentes preservadas. Faça backup antes de uma rotação planejada.')
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    private_write(folder / 'private.pem', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    private_write(folder / 'subscriptions.key', Fernet.generate_key().decode())
    private_write(folder / 'vapid.json', json.dumps({'public_key': encode(public), 'subject': subject}))
    print('Chaves Web Push geradas. Reinicie o servidor para ativá-las.')


if __name__ == '__main__':
    setup()
