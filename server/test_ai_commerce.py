import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import ai
import commerce


class AIAndCommerceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.environment = patch.dict(os.environ, {'ORBIT_AI_PROVIDER': 'ollama', 'OLLAMA_MODEL': 'local-test',
            'OLLAMA_BASE_URL': 'http://127.0.0.1:11434', 'ORBIT_AI_DAILY_REQUEST_LIMIT': '2',
            'TIKTOK_APP_KEY': 'test-key', 'TIKTOK_APP_SECRET': 'test-secret',
            'TIKTOK_REDIRECT_URI': 'http://127.0.0.1:8787/api/commerce/tiktok/callback',
            'TIKTOK_REQUIRED_SCOPES': 'creator.test'}, clear=False)
        self.environment.start()
        self.patches = [patch.object(ai, 'USAGE_DB', self.root/'usage.sqlite3'),
                        patch.object(commerce, 'DATA', self.root), patch.object(commerce, 'STORE', self.root/'commerce.sqlite3')]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.environment.stop()
        self.folder.cleanup()

    def test_paid_calls_require_explicit_enable(self):
        with patch.dict(os.environ, {'ORBIT_AI_PROVIDER': 'openai', 'ORBIT_AI_REMOTE_ENABLED': 'false', 'OPENAI_API_KEY': 'secret', 'OPENAI_MODEL': 'test'}):
            with patch.object(ai, 'request_json') as request:
                with self.assertRaises(ValueError):
                    ai.infer('task', {}, {})
                request.assert_not_called()
            self.assertNotIn('secret', json.dumps(ai.status()))

    def test_local_adapter_rejects_cloud_model(self):
        with patch.dict(os.environ, {'OLLAMA_MODEL':'remote-cloud'}), patch.object(ai, 'request_json') as request:
            with self.assertRaises(ValueError):
                ai.infer('task', {}, {})
            request.assert_not_called()

    def test_tokens_are_encrypted_and_status_contains_no_secret(self):
        data={'open_id':'creator-123', 'access_token':'private-access', 'refresh_token':'private-refresh',
              'granted_scopes':['creator.test'],'access_token_expire_in':3600}
        commerce.store_tokens(data)
        encrypted=commerce.get_setting('encrypted_tokens')
        self.assertNotIn('private-access', encrypted)
        self.assertEqual(json.loads(commerce.cipher().decrypt(encrypted.encode())), data)
        self.assertTrue(commerce.status()['connected'])
        self.assertNotIn('private-access',json.dumps(commerce.status()))

    def test_daily_allowance_is_durable(self):
        with patch.dict(os.environ, {'ORBIT_AI_PROVIDER':'openai'}):
            ai.reserve_request()
            ai.reserve_request()
            with self.assertRaises(ValueError):
                ai.reserve_request()

    def test_local_usage_does_not_consume_remote_allowance(self):
        for _ in range(3):
            ai.reserve_request()
        with patch.dict(os.environ, {'ORBIT_AI_PROVIDER':'openai'}):
            ai.reserve_request()

    def test_ollama_uses_correct_wire_contract(self):
        response = {'message': {'content': '{"answer":"ok"}'}, 'prompt_eval_count': 4, 'eval_count': 2}
        with patch.object(ai, 'request_json', return_value=response) as request:
            value, meta = ai.infer('task', {'product':'Teste'}, {'answer':'texto'})
        self.assertEqual(value['answer'], 'ok')
        self.assertEqual(meta['usage']['output_tokens'], 2)
        self.assertEqual(request.call_args.args[0], 'http://127.0.0.1:11434/api/chat')
        self.assertFalse(request.call_args.args[1]['stream'])

    def test_generation_rejects_scene_outside_duration(self):
        value = {'angles':['a','b','c'], 'hooks':['a','b','c'], 'captions':['a','b'], 'hashtags':['#a'],
                 'scenes':[{'start':0,'end':999,'text':'fala'}]}
        with patch.object(ai, 'infer', return_value=(value, {})):
            with self.assertRaises(RuntimeError):
                ai.generate({'product':'P','persona':'Público','benefit':'500ml','style':'review','duration':'30','objective':'vender'})

    def test_unverified_commercial_claim_is_rejected(self):
        with self.assertRaises(RuntimeError):
            ai.validate_product_claims({'text':'Compre pelo melhor preço do mercado.'}, 'Capacidade de 500 ml')

    def test_instructions_and_duplicate_hooks_are_not_content(self):
        for value in [{'angles':['a','b','c'],'hooks':['mesmo','mesmo','mesmo']},
                      {'angles':['a','b','c'],'hooks':['a','b','c'],'scenes':[{'text':'gancho curto'}]}]:
            with self.assertRaises(RuntimeError):
                ai.validate_editorial_content(value)

    def test_invented_quantity_replaced_and_reported(self):
        result={'hooks':['Garrafa 50:50'], 'scenes':[{'text':'capacidade 999 ml'}], 'cta':'Compre por 19,90'}
        notes=ai.validate_generated_numbers(result, {'product':'Garrafa 500 ml','benefit':'500 ml','duration':'15'})
        self.assertEqual(len(notes),3)
        self.assertNotIn('50:50',result['hooks'][0])
        self.assertNotIn('999',result['scenes'][0]['text'])
        self.assertNotIn('19,90',result['cta'])

    def test_backend_assigns_scene_times_and_normalizes_hashtags(self):
        value = {'angles':['a','b','c'], 'hooks':['a','b','c'], 'captions':['a','b'], 'hashtags':['#Produto Teste'],
                 'scenes':[{'text':'gancho'},{'text':'demonstração 500 ml (9 segundos)'},{'text':'Confira detalhes'}]}
        meta = {'provider':'ollama','model':'test','usage':{},'processing_seconds':0}
        with patch.object(ai, 'infer', return_value=(value, meta)):
            result = ai.generate({'product':'P','persona':'Público','benefit':'500ml','style':'review','duration':'15','objective':'apresentar'})
        self.assertIn('[00–03s]', result['content'])
        self.assertIn('[03–10s]', result['content'])
        self.assertIn('[10–15s]', result['content'])
        self.assertIn('#ProdutoTeste', result['content'])
        self.assertNotIn('(9 segundos)', result['content'])

    def test_analysis_rejects_fabricated_quote(self):
        names = ['Gancho','Desenvolvimento','Storytelling','Demonstração e prova','CTA']
        value = {'dimensions':[{'name':name,'reason':'reason','suggestion':'suggestion','evidence':'inexistente'} for name in names]}
        with patch.object(ai, 'infer', return_value=(value, {})):
            with self.assertRaises(RuntimeError):
                ai.enrich_analysis({}, {'transcript':'texto real', 'duration':10})

    def test_oauth_state_is_bound_and_single_use(self):
        from urllib.parse import urlparse, parse_qs
        link = commerce.start_authorization('session-a')['authorize_url']
        state = parse_qs(urlparse(link).query)['state'][0]
        with patch.object(commerce, 'exchange', return_value={'open_id':'owner', 'access_token':'secret', 'refresh_token':'r', 'granted_scopes':['creator.test']}) as exchange, patch.object(commerce, 'store_tokens') as store:
            with self.assertRaises(ValueError):
                commerce.callback('code', state, 'session-b')
            exchange.assert_not_called()
            self.assertTrue(commerce.callback('code', state, 'session-a')['connected'])
            store.assert_called_once()
            with self.assertRaises(ValueError):
                commerce.callback('code', state, 'session-a')

    def test_exchange_rejects_seller_and_missing_scopes(self):
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        for data in [{'user_type':0,'granted_scopes':['creator.test']}, {'user_type':1,'granted_scopes':[]}]:
            response = Response(json.dumps({'code':0,'data':data}).encode())
            with patch.object(commerce, 'build_opener') as opener:
                opener.return_value.open.return_value = response
                with self.assertRaises(ValueError): commerce.exchange('get', {})

    def test_folder_ignores_duplicate_files_and_preserves_errors(self):
        directory=self.root/'imports';directory.mkdir()
        file=directory/'orders.json';file.write_text('[{"id":"1"}]')
        os.utime(file,(time.time()-10,time.time()-10))
        with patch.dict(os.environ, {'ORBIT_IMPORT_DIRECTORY':str(directory)}):
            with patch('commerce.time.time',return_value=time.time()+10):
                with patch('builtins.print'):
                    importer = unittest.mock.Mock(return_value={'received':1,'changed':1})
                    first=commerce.scan_imports(importer)
                    second=commerce.scan_imports(importer)
                    self.assertEqual(first['changed'],1)
                    self.assertEqual(second['changed'],0)
                    importer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
