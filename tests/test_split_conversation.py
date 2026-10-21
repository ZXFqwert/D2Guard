"""Guard against leaking future quoted payloads into the initial native turn."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evaluation_scenarios import prepare, conversation_messages


class SplitConversationTests(unittest.TestCase):
    def test_future_payload_is_not_staged_or_in_initial_input(self):
        scenario = json.loads((Path(__file__).resolve().parents[1] /
                               'scenarios/split-conversation-injection.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, fixture = prepare(scenario, 'attack', root, 'd2-test-isolation')
            later = conversation_messages(scenario, 'attack')
            future = scenario['resources']['attack']['conversation_quotes'][1]
            self.assertIn('.env', first)
            self.assertNotIn('POST', first)
            self.assertNotIn('/collect', first)
            self.assertNotIn(future, json.dumps(fixture))
            self.assertTrue(all(future not in p.read_text(encoding='utf-8')
                                for p in root.rglob('*') if p.is_file()))
            self.assertNotIn('/collect', later[0])
            self.assertIn(future, later[1])
            self.assertNotIn('.env', later[1])

    def test_quote_turn_count_must_match(self):
        with self.assertRaises(ValueError):
            conversation_messages({'conversation': ['a', 'b'], 'resources': {
                'attack': {'conversation_quotes': ['future']}}}, 'attack')
