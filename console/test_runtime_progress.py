import json
import tempfile
import time
import unittest
from pathlib import Path

from server import Console


class RuntimeProgressTests(unittest.TestCase):
    def test_reasoning_content_never_enters_progress_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            console = Console(tmp, 'python')
            folder = Path(tmp)/'runs'/'example'
            folder.mkdir(parents=True)
            (folder/'gateway.jsonl').write_text(json.dumps({'type':'proxy_request','request_id':'r','timestamp_ns':time.time_ns()-10_000_000_000})+'\n')
            (folder/'pi-events.jsonl').write_text(json.dumps({'type':'message_update','assistantMessageEvent':{'type':'thinking_delta','delta':'private reasoning'}})+'\n')
            result = console._runtime_progress('example')
            self.assertEqual(result['phase'], 'thinking')
            self.assertGreaterEqual(result['request_seconds'], 10)
            self.assertNotIn('private reasoning', json.dumps(result))

    def test_completed_transport_is_not_shown_as_generating(self):
        with tempfile.TemporaryDirectory() as tmp:
            console = Console(tmp, 'python')
            folder = Path(tmp)/'runs'/'example'
            folder.mkdir(parents=True)
            (folder/'gateway.jsonl').write_text('\n'.join(json.dumps(x) for x in [
                {'type':'proxy_request','request_id':'r','timestamp_ns':time.time_ns()},
                {'type':'proxy_response','request_id':'r'}]))
            self.assertIsNone(console._runtime_progress('example'))
