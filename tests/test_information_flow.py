import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_information_flow import audit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from original_laya import payload_for


class FlowAuditTests(unittest.TestCase):
    def test_detects_transport_mismatch_and_missing_model_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native = [
                {'type':'message_end','message':{'role':'user','content':[{'type':'text','text':'Read docs'}]}},
                {'type':'message_end','message':{'role':'assistant','content':[
                    {'type':'text','text':'I will read the document.'},
                    {'type':'toolCall','id':'c1','name':'fs_read','arguments':{'path':'README.md'}}]}},
                {'type':'message_end','message':{'role':'toolResult','toolCallId':'c1','isError':False,
                    'content':[{'type':'text','text':'original'}]}},
            ]
            observed = [
                {'type':'agent_start','task':'Read docs'},
                {'type':'tool_proposed','call_id':'c1','args':{'path':'WRONG.md'}},
                {'type':'guard_decision','call_id':'c1','args':{'path':'README.md'}},
                {'type':'tool_result','call_id':'c1','text':'modified'},
                {'type':'model_response','status':200},
            ]
            core = [{'type':'core_ingest','call_id':'c1','event_type':'TOOL_RETURN',
                     'raw_sha256':hashlib.sha256(b'modified').hexdigest()}]
            for name, rows in [('pi-events.jsonl',native),('audit.jsonl',observed),('core.jsonl',core)]:
                (root/name).write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
            result = audit(root)
            self.assertTrue(result['user_task_equal'])
            self.assertEqual(result['equal_args_at_plugin_and_decision'],0)
            self.assertEqual(result['equal_successful_returns_at_plugin'],0)
            self.assertEqual(result['equal_successful_returns_at_core_sha256'],0)
            self.assertEqual(result['native_assistant_public_text_messages'],1)
            self.assertEqual(result['observed_model_response_payloads'],0)

    def test_original_adapter_rejects_legacy_raw_text_envelope(self):
        with self.assertRaises(ValueError):
            payload_for({}, {'nested':{'tool_args':{'body':'secret'}}})
        result = payload_for({'authorization_known':False}, {'event_kind':'tool_return','facts':[]})
        self.assertEqual(set(result), {'previous_security_state','security_delta'})
