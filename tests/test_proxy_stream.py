import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from proxy_stream import forward


class ProxyStreamTests(unittest.TestCase):
    def run_stream(self, chunks=(), failure=None, writer=None):
        handler=MagicMock();handler.wfile=writer or io.BytesIO()
        upstream=MagicMock();upstream.status_code=200
        upstream.headers={'content-type':'text/event-stream'}
        upstream.iter_bytes.return_value=iter(chunks)
        client=MagicMock()
        if failure:client.stream.side_effect=failure
        else:client.stream.return_value.__enter__.return_value=upstream
        log=[]
        with patch('proxy_stream.httpx.Client') as factory:
            factory.return_value.__enter__.return_value=client
            forward(handler,{'base_url':'https://example.invalid/v1','api_key':'unit-test-only'},
                    '/responses',b'{}',lambda name,item:log.append(item),'request-1')
        return handler,log

    def test_exact_bytes_status_and_correlation(self):
        handler,log=self.run_stream([b'data: one\n\n',b'data: two\n\n'])
        self.assertEqual(handler.wfile.getvalue(),b'data: one\n\ndata: two\n\n')
        self.assertTrue(log[0]['transport_complete'])
        self.assertEqual(log[0]['upstream_bytes'],log[0]['downstream_bytes'])
        self.assertEqual(log[0]['request_id'],'request-1')

    def test_upstream_connect_failure_produces_one_502_without_secret_log(self):
        handler,log=self.run_stream(failure=httpx.ConnectError('unit-test-only private request body'))
        self.assertEqual(handler.respond.call_args.args[0],502)
        self.assertEqual(log[0]['stage'],'connect_upstream')
        self.assertNotIn('unit-test-only',json.dumps(log))

    def test_downstream_abort_retains_partial_evidence_without_second_headers(self):
        writer=MagicMock();writer.write.side_effect=ConnectionAbortedError(10053,'private body')
        handler,log=self.run_stream([b'partial'],writer=writer)
        self.assertEqual(log[0]['stage'],'write_downstream')
        self.assertEqual(log[0]['upstream_bytes'],7)
        self.assertEqual(log[0]['downstream_bytes'],0)
        self.assertFalse(log[0]['transport_complete'])
        handler.respond.assert_not_called()
        self.assertNotIn('private body',json.dumps(log))

    def test_upstream_midstream_error_does_not_append_second_http_response(self):
        def chunks():
            yield b'first'
            raise httpx.ReadError('connection reset')
        handler,log=self.run_stream(chunks())
        self.assertEqual(log[0]['stage'],'read_upstream')
        self.assertEqual(log[0]['downstream_bytes'],5)
        self.assertEqual(log[0]['chunks'],1)
        handler.respond.assert_not_called()
