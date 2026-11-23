import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import io
import app
import media


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.patcher = patch.object(app, 'DATABASE', Path(self.folder.name) / 'test.sqlite3')
        self.patcher.start()
        self.db = app.connect()

    def tearDown(self):
        self.db.close()
        self.patcher.stop()
        self.folder.cleanup()

    def order(self, **changes):
        return dict(id='1', product='Produto', gmv=100, commission=15, date='2026-11-20', **changes)

    def test_demo_requires_explicit_action(self):
        self.assertEqual(app.records(self.db, 'orders'), [])
        app.dispatch(self.db, '/api/demo', {})
        self.assertEqual(len(app.records(self.db, 'orders')), 4)
        self.assertTrue(all(row['source'] == 'demo' for row in app.records(self.db, 'orders')))

    def test_repeated_import_deduplicates_and_updates(self):
        self.assertEqual(app.import_orders(self.db, [self.order()])['changed'], 1)
        self.assertEqual(app.import_orders(self.db, [self.order()])['changed'], 0)
        self.assertEqual(len(app.records(self.db, 'notifications')), 1)
        self.assertEqual(app.import_orders(self.db, [self.order(status='reembolsado')])['changed'], 1)
        self.assertEqual(len(app.records(self.db, 'orders')), 1)

    def test_accounts_are_distinct(self):
        app.import_orders(self.db, [self.order(account='A'), self.order(account='B')])
        self.assertEqual(len(app.records(self.db, 'orders')), 2)

    def test_order_group_and_original_day_survive_partial_reimport(self):
        row = self.order(order_id='pedido-principal')
        app.import_orders(self.db, [row])
        row.pop('date')
        row.pop('order_id')
        result = app.import_orders(self.db, [row])
        self.assertEqual(result['unchanged'], 1)
        stored = app.records(self.db, 'orders')[0]
        self.assertEqual(stored['order_id'], 'pedido-principal')
        self.assertEqual(stored['date'], '2026-11-20')

    def test_validation_before_mutation(self):
        with self.assertRaises(ValueError):
            app.import_orders(self.db, [self.order(), self.order(quantity=-1)])
        self.assertEqual(app.records(self.db, 'orders'), [])

    def test_reject_non_finite_money(self):
        order = self.order()
        order['gmv'] = float('nan')
        with self.assertRaises(ValueError):
            app.import_orders(self.db, [order])

    def test_analysis_is_explicit_and_has_no_fabricated_timestamps(self):
        result = app.analyze({'transcript': 'Veja o produto em uso e confira os detalhes.', 'duration': 20})
        self.assertIn('Regras', result['method'])
        self.assertTrue(all(item['timestamp'] is None for item in result['dimensions']))

    def test_media_rejects_wrong_mime_before_reading(self):
        with self.assertRaises(ValueError):
            media.receive_and_transcribe(io.BytesIO(b'hello'), 5, 'video.mp4', 'text/plain')

    def test_media_rejects_large_body_before_reading(self):
        with self.assertRaises(ValueError):
            media.receive_and_transcribe(io.BytesIO(), media.MAX_VIDEO_BYTES + 1, 'video.mp4', 'video/mp4')

    def test_media_interrupted_upload(self):
        with self.assertRaises(ValueError):
            media.receive_and_transcribe(io.BytesIO(b'abc'), 100, 'video.mp4', 'video/mp4')


if __name__ == '__main__':
    unittest.main()
