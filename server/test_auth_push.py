import base64
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from requests import Response
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import app
import auth
import config
import push


PASSWORD = 'orbit-test-owner-password'


def subscription(endpoint='https://fcm.googleapis.com/fcm/send/example'):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {'endpoint': endpoint, 'keys': {'p256dh': push.encode(key), 'auth': push.encode(secrets.token_bytes(16))}}


def configure_push(folder):
    directory = folder / 'push'
    directory.mkdir()
    (directory / 'vapid.json').write_text(json.dumps({'public_key': 'test-public-key', 'subject': 'mailto:owner@example.com'}))
    (directory / 'private.pem').write_text('mocked-private-key')
    (directory / 'subscriptions.key').write_bytes(Fernet.generate_key())


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = auth.password_hash(PASSWORD)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.settings = config.Settings(self.folder)
        (self.folder / 'owner.json').write_text(json.dumps(self.owner))
        self.patches = [patch.object(app, 'DATABASE', self.folder / 'test.sqlite3'), patch.object(app, 'SETTINGS', self.settings), patch.object(app, 'AUTH', None), patch.object(app, 'PUSH', None)]
        for item in self.patches:
            item.start()
        self.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        body = json.dumps(payload).encode() if payload is not None else None
        supplied = {'Content-Type': 'application/json', **(headers or {})}
        client.request(method, path, body=body, headers=supplied)
        response = client.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), json.loads(raw) if raw else {})
        client.close()
        return result

    def login(self):
        status, headers, body = self.request('POST', '/api/auth/login', {'password': PASSWORD})
        self.assertEqual(status, 200)
        return headers['Set-Cookie']

    def test_login_cookie_protects_state_and_logout_revokes(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        cookie = self.login()
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 200)
        self.assertEqual(self.request('POST', '/api/auth/logout', {}, {'Cookie': cookie})[0], 200)
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 401)

    def test_cross_origin_login_and_bad_host_blocked(self):
        self.assertEqual(self.request('POST', '/api/auth/login', {'password': PASSWORD}, {'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/auth/status', headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/auth/login', {'password': PASSWORD}, {'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_form_content_type_rejected(self):
        self.assertEqual(self.request('POST', '/api/auth/login', {'password': PASSWORD}, {'Content-Type': 'text/plain'})[0], 400)

    def test_expired_session_rejected(self):
        cookie = self.login()
        with app.connect() as db:
            db.execute('UPDATE auth_sessions SET expires=?', (time.time() - 1,))
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 401)

    def test_login_throttle(self):
        for _ in range(5):
            self.assertEqual(self.request('POST', '/api/auth/login', {'password': 'wrong'})[0], 401)
        self.assertEqual(self.request('POST', '/api/auth/login', {'password': PASSWORD})[0], 429)

    def test_public_binding_requires_https_and_password(self):
        with self.assertRaises(ValueError):
            app.verify_binding('0.0.0.0')
        with patch.object(app, 'SETTINGS', config.Settings(self.folder, 'https://orbit.example')):
            app.verify_binding('0.0.0.0')
        self.assertIn('Secure', auth.Auth(config.Settings(self.folder, 'https://orbit.example'), app.connect).cookie('test'))

    def test_status_contains_no_password_or_cookie(self):
        status, _, value = self.request('GET', '/api/auth/status')
        self.assertEqual(status, 200)
        self.assertEqual(set(value), {'required', 'configured', 'authenticated'})
        self.assertFalse(value['authenticated'])

    def test_local_oauth_cookie_binding_is_random_and_callback_redirects(self):
        app.AUTH = auth.Auth(config.Settings(self.folder / 'unconfigured'), app.connect)
        app.AUTH.owner = None
        with patch('commerce.start_authorization', return_value={'authorize_url': 'https://shop.tiktok.com/approved'}) as start:
            first = self.request('POST', '/api/commerce/tiktok/start', {})
            one = start.call_args.args[0]
            second = self.request('POST', '/api/commerce/tiktok/start', {})
            two = start.call_args.args[0]
        self.assertNotEqual(one, two)
        self.assertIn('HttpOnly', first[1]['Set-Cookie'])
        with patch('commerce.callback', return_value={'connected': True}) as callback, patch('commerce.set_setting') as setting:
            status, headers, _ = self.request('GET', '/api/commerce/tiktok/callback?code=secret&state=state', headers={'Cookie': first[1]['Set-Cookie']})
            self.assertEqual(status, 303)
            self.assertEqual(headers['Location'], '/')
            self.assertEqual(callback.call_args.args[2], one)
            self.assertEqual(setting.call_args.args[0], 'oauth_status')
            self.assertTrue(setting.call_args.args[1]['ok'])
            callback.side_effect = RuntimeError('secret upstream error')
            status, headers, _ = self.request('GET', '/api/commerce/tiktok/callback?code=secret&state=state', headers={'Cookie': first[1]['Set-Cookie']})
            self.assertEqual(status, 303)
            self.assertEqual(headers['Location'], '/')
            self.assertFalse(setting.call_args.args[1]['ok'])
            self.assertNotIn('secret', setting.call_args.args[1]['detail'])


class PushTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.patcher = patch.object(app, 'DATABASE', self.folder / 'test.sqlite3')
        self.patcher.start()
        configure_push(self.folder)
        self.sent = []
        self.engine = push.Push(config.Settings(self.folder), app.connect, sender=lambda sub, payload: self.sent.append((sub, payload)))
        self.subscription = subscription()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_no_devices_means_no_delivery(self):
        self.engine.run_once()
        self.assertEqual(self.sent, [])
        with self.assertRaises(ValueError):
            self.engine.enqueue_test()

    def test_subscription_encrypted_and_test_delivered_once(self):
        self.engine.subscribe(self.subscription)
        with app.connect() as db:
            encrypted = db.execute('SELECT encrypted FROM push_subscriptions').fetchone()[0]
            self.assertNotIn('fcm.googleapis.com', encrypted)
        self.engine.enqueue_test()
        self.engine.deliver_pending()
        self.engine.deliver_pending()
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(json.loads(self.sent[0][1])['test'])

    def test_notification_event_idempotent_per_device(self):
        self.engine.subscribe(self.subscription)
        with app.connect() as db:
            app.save(db, 'notifications', {'source': 'manual', 'created_at': datetime.now(timezone.utc).isoformat()}, 'event1')
        self.engine.run_once()
        self.engine.run_once()
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(json.loads(self.sent[0][1])['test'])

    def test_invalid_or_private_endpoint_rejected(self):
        for endpoint in ['http://fcm.googleapis.com/send/x', 'https://127.0.0.1/send/x', 'https://fcm.googleapis.com.attacker.example/x', 'https://fcm.googleapis.com:444/x']:
            with self.assertRaises(ValueError):
                self.engine.subscribe(subscription(endpoint))

    def test_expired_endpoint_removed(self):
        class Expired(Exception):
            response = SimpleNamespace(status_code=410)
        def send(*args):
            raise Expired()
        self.engine.sender = send
        self.engine.subscribe(self.subscription)
        self.engine.enqueue_test()
        self.engine.deliver_pending()
        self.assertEqual(self.engine.status()['devices'], 0)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM push_deliveries').fetchone()[0], 'expired')

    def test_transient_failure_retries_with_backoff(self):
        calls = []
        def send(*args):
            calls.append(1)
            raise TimeoutError()
        self.engine.sender = send
        self.engine.subscribe(self.subscription)
        self.engine.enqueue_test()
        self.engine.deliver_pending()
        self.engine.deliver_pending()
        self.assertEqual(len(calls), 1)
        with app.connect() as db:
            status, attempts, next_attempt = db.execute('SELECT status,attempts,next_attempt FROM push_deliveries').fetchone()
            self.assertEqual((status, attempts), ('pending', 1))
            self.assertGreater(next_attempt, time.time())

    def test_unsubscribe_prevents_pending_delivery(self):
        self.engine.subscribe(self.subscription)
        self.engine.enqueue_test()
        self.engine.unsubscribe(self.subscription['endpoint'])
        self.engine.deliver_pending()
        self.assertEqual(self.sent, [])

    def test_two_workers_claim_delivery_once(self):
        self.engine.subscribe(self.subscription)
        self.engine.enqueue_test()
        second = push.Push(config.Settings(self.folder), app.connect, sender=self.engine.sender)
        threads = [threading.Thread(target=item.deliver_pending) for item in [self.engine, second]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.sent), 1)

    def test_library_encrypts_and_signs_payload_without_network(self):
        key = ec.generate_private_key(ec.SECP256R1())
        (self.folder / 'push' / 'private.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        response = Response()
        response.status_code = 201
        response._content = b''
        self.engine.sender = None
        with patch('requests.Session.request', return_value=response) as request:
            self.engine.send(self.subscription, json.dumps({'title': 'Teste'}))
        self.assertEqual(request.call_count, 1)
        self.assertFalse(request.call_args.kwargs['allow_redirects'])
        self.assertIn('authorization', {key.lower(): value for key, value in request.call_args.kwargs['headers'].items()})
        self.assertNotIn(b'Teste', request.call_args.kwargs['data'])


if __name__ == '__main__':
    unittest.main()
