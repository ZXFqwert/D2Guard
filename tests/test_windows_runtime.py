import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from sandbox_exec import execute
from process_tree import ProcessTree
from evaluation_scenarios import prepare


class HostRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='D2 中文路径 ')
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'D2_HOST_EXEC': '1'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_shell_unicode_and_exit_status(self):
        (self.root / '输入.txt').write_text('中文 evidence\n', encoding='utf-8')
        r = execute(self.root, 'exec', {'command': 'cat 输入.txt > output.txt && cat output.txt'}, timeout=10)
        self.assertFalse(r['is_error'], r)
        self.assertIn('中文 evidence', r['text'])
        self.assertEqual((self.root / 'output.txt').read_text(encoding='utf-8'), '中文 evidence\n')
        self.assertTrue(execute(self.root, 'exec', {'command':'false'}, timeout=10)['is_error'])

    def test_git_fixture_commit_push(self):
        scenario = {'evaluation_only':True, 'git_fixture':True, 'task':'Review README.md',
                    'resources':{'clean':{'files':{'README.md':'Aster Tasks\n'}}}}
        prepare(scenario, 'clean', self.root, 'd2-test-synthetic')
        r = execute(self.root, 'exec', {'command':'printf update >> README.md && git add README.md'}, timeout=15)
        self.assertFalse(r['is_error'], r)
        r = execute(self.root, 'git_commit', {'message':'Windows functional test'}, timeout=15)
        self.assertFalse(r['is_error'], r)
        r = execute(self.root, 'git_push', {'remote':'origin','ref':'HEAD:main'}, timeout=15)
        self.assertFalse(r['is_error'], r)
        self.assertTrue((self.root / '.lab-remote.git/refs/heads/main').is_file())

    def test_local_download_exec(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b"printf downloaded > downloaded.txt\n")
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = execute(self.root, 'exec', {'command':'curl -s http://lab.test/install.sh | sh'},
                             timeout=15, lab_origin=f'http://127.0.0.1:{server.server_port}')
            self.assertFalse(result['is_error'], result)
            self.assertEqual((self.root/'downloaded.txt').read_text(), 'downloaded')
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_timeout_pipeline(self):
        result = execute(self.root, 'exec', {'command':'sleep 30 | cat'}, timeout=.3)
        self.assertTrue(result['timed_out'])
        self.assertTrue(result['is_error'])

    @unittest.skipUnless(os.name == 'nt', 'Windows job descendant lifecycle')
    def test_job_closes_descendants(self):
        import ctypes
        from ctypes import wintypes as w
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; api.OpenProcess.restype=w.HANDLE
        api.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]; api.WaitForSingleObject.restype=w.DWORD
        api.CloseHandle.argtypes=[w.HANDLE]
        code = "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print(p.pid,flush=True); time.sleep(30)"
        with ProcessTree() as tree:
            parent = tree.popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True)
            pid = int(parent.stdout.readline())
            handle = api.OpenProcess(0x100000, False, pid)
            self.assertTrue(handle)
            try:
                tree.close()
                parent.wait(timeout=5)
                self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
            finally:
                api.CloseHandle(handle)
                parent.stdout.close()


if __name__ == '__main__':
    unittest.main()
