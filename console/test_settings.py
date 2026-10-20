import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
import server


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'.local').mkdir()
        (self.root/'.local/provider.json').write_text(json.dumps({'base_url': 'https://a.test/v1', 'api_key': 'd2-test-agent',
                                                                   'main_model': 'm1', 'api_style': 'chat_completions'}))
        with patch.object(server, 'HERE', self.root):
            self.console = server.Console(self.root, 'python')

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self, name):
        return json.loads((self.root/'.local'/name).read_text())

    def test_keys_are_never_returned(self):
        view = self.console.settings()
        self.assertNotIn('d2-test-agent', json.dumps(view))
        self.assertTrue(view['agent']['has_key'])
        self.assertFalse(view['review']['separate'])

    def test_stored_key_only_goes_to_its_own_address(self):
        code, out = self.console.save_settings({'agent': {'base_url': 'https://other.test/v1', 'model': 'm2'}})
        self.assertEqual(code, 400)
        self.assertEqual(self.saved('provider.json')['base_url'], 'https://a.test/v1')
        code, _ = self.console.save_settings({'agent': {'model': 'm2'}})
        self.assertEqual(code, 200)
        self.assertEqual(self.saved('provider.json')['api_key'], 'd2-test-agent')
        self.assertEqual(self.saved('provider.json')['main_model'], 'm2')

    def test_reasoning_capability_survives_model_edits_and_can_be_disabled(self):
        code, view = self.console.save_settings({'agent': {'reasoning_capable': True}})
        self.assertEqual(code, 200)
        self.assertTrue(view['reasoning_capable'])
        self.console.save_settings({'agent': {'model': 'm2'}})
        self.assertTrue(self.saved('provider.json')['reasoning_capable'])
        self.console.save_settings({'agent': {'reasoning_capable': False}})
        self.assertFalse(self.saved('provider.json')['reasoning_capable'])

    def test_invalid_reasoning_capability_is_rejected(self):
        code, _ = self.console.save_settings({'agent': {'reasoning_capable': 'false'}})
        self.assertEqual(code, 400)
        self.assertNotIn('reasoning_capable', self.saved('provider.json'))

    def test_separate_review_model_reuses_key_on_same_service(self):
        code, view = self.console.save_settings({'agent': {}, 'review': {'separate': True, 'base_url': 'https://a.test/v1', 'model': 'judge'}})
        self.assertEqual(code, 200)
        self.assertTrue(view['review']['separate'])
        self.assertNotIn('api_key', self.saved('review.json'))
        import lab
        review, separate = lab.review_configuration(self.saved('provider.json'), self.root)
        self.assertTrue(separate)
        self.assertEqual((review['main_model'], review['api_key']), ('judge', 'd2-test-agent'))
        self.console.save_settings({'agent': {}, 'review': {'separate': False}})
        review, separate = lab.review_configuration(self.saved('provider.json'), self.root)
        self.assertFalse(separate)
        self.assertEqual(review['main_model'], 'm1')

    def test_other_origins_cannot_use_the_api(self):
        httpd = server.LocalHTTPServer(('127.0.0.1', 0), server.make_handler(self.console))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{httpd.server_port}'
            def put(origin):
                request = urllib.request.Request(base + '/api/settings', data=b'{"agent":{"model":"x"}}', method='PUT',
                                                 headers={'Content-Type': 'application/json', **({'Origin': origin} if origin else {})})
                try:
                    with server.DIRECT.open(request, timeout=5) as response:
                        return response.status
                except urllib.error.HTTPError as exc:
                    return exc.code
            self.assertEqual(put('https://evil.example'), 403)
            self.assertEqual(put(base), 200)
            self.assertEqual(put(None), 200)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == '__main__':
    unittest.main()
