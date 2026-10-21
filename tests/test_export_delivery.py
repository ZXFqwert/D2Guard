"""Delivery export scan: infrastructure blocklist is read from the ignored .local/ directory."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('export_delivery', ROOT / 'tools' / 'export_delivery.py')
export_delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_delivery)


class BlocklistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'root'
        self.folder = Path(self.tmp.name) / 'out'
        (self.root / '.local').mkdir(parents=True)
        self.folder.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_empty_list(self):
        self.assertEqual(export_delivery.blocklist(self.root), [])

    def test_reads_terms_skipping_blank_and_comment_lines(self):
        (self.root / '.local' / 'delivery-blocklist.txt').write_text('# note\n\nhost.internal.test\n 10.9.8.7 \n', encoding='utf-8')
        self.assertEqual(export_delivery.blocklist(self.root), ['host.internal.test', '10.9.8.7'])

    def test_scan_blocks_files_containing_listed_terms(self):
        (self.root / '.local' / 'delivery-blocklist.txt').write_text('host.internal.test\n', encoding='utf-8')
        (self.folder / 'bad.json').write_text('{"base_url": "https://api.host.internal.test/v1"}', encoding='utf-8')
        (self.folder / 'good.json').write_text('{"base_url": "https://upstream.example/v1"}', encoding='utf-8')
        result = export_delivery.scan(self.folder, self.root)
        self.assertFalse(result['passed'])
        self.assertEqual(result['blocked_files'], ['bad.json'])
        self.assertEqual(result['blocklist_terms'], 1)

    def test_scan_without_blocklist_passes_clean_files(self):
        (self.folder / 'good.json').write_text('{"base_url": "https://upstream.example/v1"}', encoding='utf-8')
        self.assertTrue(export_delivery.scan(self.folder, self.root)['passed'])

    def test_source_contains_no_literal_infrastructure_terms(self):
        source = (ROOT / 'tools' / 'export_delivery.py').read_text(encoding='utf-8')
        for term in export_delivery.blocklist():
            self.assertNotIn(term, source)


if __name__ == '__main__':
    unittest.main()
