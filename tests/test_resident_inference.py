import unittest
from unittest.mock import Mock

from inference_pool import RemoteFast
from d2v2.normalization import evidence_span


class ResidentInferenceTests(unittest.TestCase):
    def test_original_token_spans_survive_resident_transport(self):
        client=Mock()
        client.info={'fast':{'revision':'pinned'}}
        client.call.return_value=[[0,1],[1,2],[2,5],[6,9]]
        fast=RemoteFast(client)
        ref=evidence_span({'event_id':'x'},'AB中文 CD', [2,5],fast)
        self.assertEqual(ref['token_span'],[2,3])
        self.assertEqual(ref['tokenizer'],'original-laya:pinned')
        self.assertEqual(fast.token_span('AB中文 CD',[5,6]),[0,0])
        client.call.assert_called_with('token_offsets',text='AB中文 CD')

    def test_resident_credentials_are_host_only(self):
        from lab import pi_environment
        env=pi_environment({'PATH':'x','D2_INFERENCE_DESCRIPTOR':'private','D2_APPROVAL_CREDENTIAL':'secret'})
        self.assertEqual(env,{'PATH':'x'})
