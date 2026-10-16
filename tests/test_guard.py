import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from guard import Guard

class GuardTests(unittest.TestCase):
    def test_actual_read_required_and_mode_does_not_change_observation(self):
        for enabled in (False, True):
            g = Guard(enabled)
            proposal = {'body': 'TOKEN=synthetic-credential-123'}
            self.assertEqual(g.decide('net_fetch', proposal)['verdict'], 'ALLOW')
            event = {'type': 'tool_result', 'tool': 'fs_read', 'call_id': 'read-1',
                'agent_id': 'main', 'args': {'path': '.env'}, 'text': 'TOKEN=synthetic-credential-123'}
            g.observe({**event, 'is_error': True})
            self.assertFalse(g.decide('net_fetch', proposal)['would_block'])
            g.observe(event)
            result = g.decide('net_fetch', proposal)
            self.assertTrue(result['would_block'])
            self.assertEqual(result['verdict'], 'BLOCK' if enabled else 'ALLOW')
            self.assertEqual(result['evidence']['source_call_id'], 'read-1')
            self.assertEqual(g.decide('net_fetch', {'body': 'ordinary status'})['verdict'], 'ALLOW')

    def test_child_credential_transfer_uses_observed_parent_data(self):
        g = Guard(True)
        g.observe({'type':'tool_result','tool':'fs_read','call_id':'read-2','agent_id':'main',
            'args':{'path':'.env'},'text':'API_KEY=synthetic-credential-abc'})
        self.assertEqual(g.decide('spawn_subagent', {'task':'Process synthetic-credential-abc'})['verdict'], 'BLOCK')
        self.assertEqual(g.decide('spawn_subagent', {'task':'Summarize README.md'})['verdict'], 'ALLOW')

if __name__ == '__main__':
    unittest.main()
