import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import app
import commerce


class CommerceImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.directory = self.root / 'imports'
        self.directory.mkdir()
        self.patches = [patch.object(app, 'DATABASE', self.root / 'app.sqlite3'), patch.object(commerce, 'DATA', self.root), patch.object(commerce, 'STORE', self.root / 'commerce.sqlite3'), patch.dict(os.environ, {'ORBIT_IMPORT_DIRECTORY': str(self.directory)})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def order(self, **changes):
        value = dict(id='0001', product='Produto, edição especial', gmv='129.90', commission='19.49', status='pago', date='2026-11-21', account='Perfil A', quantity='2', commission_status='estimada')
        value.update(changes)
        return value

    def csv(self, rows=None, delimiter=',', extra=()):
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=[*commerce.CSV_COLUMNS, *extra], delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows or [self.order()])
        return output.getvalue().encode('utf-8')

    def write(self, name, content):
        path = self.directory / name
        path.write_bytes(content)
        os.utime(path, (time.time() - 10, time.time() - 10))
        return path

    def importer(self, items):
        with app.connect() as db:
            return app.import_orders(db, items, 'manual')

    def test_comma_csv_preserves_quoted_product_and_zero_id(self):
        orders = commerce.parse_import(self.csv(), '.CSV')
        self.assertEqual(orders[0]['id'], '0001')
        self.assertEqual(orders[0]['product'], 'Produto, edição especial')
        self.assertEqual(orders[0]['gmv'], 129.9)
        self.assertEqual(orders[0]['quantity'], 2)

    def test_bom_semicolon_decimal_comma_and_optional_order_id(self):
        data = self.csv([self.order(gmv='129,90', commission='19,49', currency='BRL', order_id='PEDIDO-1')], ';', ('currency', 'order_id'))
        result = commerce.parse_import(b'\xef\xbb\xbf' + data, 'csv')
        self.assertEqual(result[0]['commission'], 19.49)
        self.assertEqual(result[0]['order_id'], 'PEDIDO-1')

    def test_rejects_bad_money_quantity_and_status_before_import(self):
        for changes in [{'gmv': '-1'}, {'gmv': 'NaN'}, {'gmv': '1.234,56'}, {'gmv': '1.234'}, {'gmv': '1e3'}, {'quantity': '1.5'}, {'quantity': '0'}, {'status': 'PAID'}, {'commission_status': 'paga'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                commerce.parse_import(self.csv([self.order(**changes)]), 'csv')

    def test_rejects_foreign_currency_and_naive_datetime(self):
        with self.assertRaises(ValueError):
            commerce.parse_import(self.csv([self.order(currency='USD')], extra=('currency',)), 'csv')
        for date in ['21/11/2026', '2026-02-30', '2026-11-21T14:00:00']:
            with self.subTest(date=date), self.assertRaises(ValueError):
                commerce.parse_import(self.csv([self.order(date=date)]), 'csv')
        orders = commerce.parse_import(self.csv([self.order(date='2026-11-21T14:00:00-03:00')]), 'csv')
        self.assertIn('-03:00', orders[0]['date'])

    def test_rejects_duplicate_missing_and_unknown_headers(self):
        for content in [b'id,id,product\n1,2,P\n', b'id,product\n1,P\n', self.csv().replace(b'id,product', b'unknown,product', 1)]:
            with self.subTest(content=content[:30]), self.assertRaises(ValueError):
                commerce.parse_import(content, 'csv')

    def test_duplicate_item_id_rejected_but_accounts_distinct(self):
        with self.assertRaises(ValueError):
            commerce.parse_import(self.csv([self.order(), self.order(commission='20')]), 'csv')
        result = commerce.parse_import(self.csv([self.order(), self.order(account='Perfil B')]), 'csv')
        self.assertEqual(len(result), 2)

    def test_malformed_encoding_empty_csv_and_missing_field_rejected(self):
        for data in [b'\xff\xfe\x01', b'', ','.join(commerce.CSV_COLUMNS).encode(), self.csv().replace(b',estimada', b'', 1)]:
            with self.subTest(data=data[:20]), self.assertRaises(ValueError):
                commerce.parse_import(data, 'csv')

    def test_size_limit_and_json_contract(self):
        with self.assertRaises(ValueError):
            commerce.parse_import(b'x' * (commerce.MAX_IMPORT_BYTES + 1), 'csv')
        self.assertEqual(commerce.parse_import(json.dumps({'orders': [self.order()]}).encode(), 'json')[0]['id'], '0001')
        for content, suffix in [(b'[]', 'json'), (b'{}', 'json'), (b'null', 'json'), (b'[]', 'xlsx')]:
            with self.assertRaises(ValueError):
                commerce.parse_import(content, suffix)

    def test_scanner_persists_manual_source_provenance_and_deduplicates(self):
        content = self.csv()
        self.write('orders.CSV', content)
        first = commerce.scan_imports(self.importer)
        second = commerce.scan_imports(self.importer)
        self.assertEqual(first['changed'], 1)
        self.assertEqual(second['changed'], 0)
        self.assertEqual(first['sources'][0]['sha256'], hashlib.sha256(content).hexdigest())
        self.assertEqual(commerce.status()['imports']['sources']['orders.CSV']['sha256'], hashlib.sha256(content).hexdigest())
        with app.connect() as db:
            orders = app.records(db, 'orders')
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]['source'], 'manual')
            self.assertEqual(len(app.records(db, 'notifications')), 1)

    def test_scanner_updates_commission_and_refund_without_duplicate_records(self):
        self.write('orders.csv', self.csv())
        commerce.scan_imports(self.importer)
        self.write('orders.csv', self.csv([self.order(commission='0', status='reembolsado')]))
        self.assertEqual(commerce.scan_imports(self.importer)['changed'], 1)
        with app.connect() as db:
            orders = app.records(db, 'orders')
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]['status'], 'reembolsado')
            self.assertEqual(orders[0]['commission'], 0)

    def test_invalid_second_row_is_atomic_and_can_be_corrected(self):
        path = self.write('orders.csv', self.csv([self.order(), self.order(id='2', commission='NaN')]))
        result = commerce.scan_imports(self.importer)
        self.assertEqual(result['files'], 0)
        self.assertIn('Linha 3', result['errors'][0]['error'])
        with app.connect() as db:
            self.assertEqual(app.records(db, 'orders'), [])
        self.write(path.name, self.csv([self.order(), self.order(id='2')]))
        self.assertEqual(commerce.scan_imports(self.importer)['changed'], 2)

    def test_two_scans_import_same_file_once(self):
        self.write('orders.csv', self.csv())
        reports = []
        threads = [threading.Thread(target=lambda: reports.append(commerce.scan_imports(self.importer))) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(report['changed'] for report in reports), 1)

    def test_oversized_file_reported_and_fresh_file_deferred(self):
        self.write('oversized.csv', b'x' * (commerce.MAX_IMPORT_BYTES + 1))
        (self.directory / 'fresh.csv').write_bytes(self.csv())
        result = commerce.scan_imports(self.importer)
        self.assertEqual(result['files'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('2 MB', result['errors'][0]['error'])

    def test_file_removed_during_read_does_not_abort_other_files(self):
        removed = self.write('a-removed.csv', self.csv())
        self.write('b-valid.csv', self.csv())
        original_open = Path.open
        def open_file(path, *args, **kwargs):
            if path == removed and args and args[0] == 'rb':
                path.unlink()
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', new=open_file):
            report = commerce.scan_imports(self.importer)
        self.assertEqual(report['changed'], 1)
        self.assertEqual(len(report['errors']), 1)
        self.assertEqual(report['errors'][0]['file'], removed.name)


if __name__ == '__main__':
    unittest.main()
