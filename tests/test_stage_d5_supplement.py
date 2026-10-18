import unittest
from stage_d5_supplement import decisions_for


class SupplementDecisionTests(unittest.TestCase):
    def decision(self, **changes):
        return {**dict(id='a',label='request',kind='concrete_task',reason='current task',reviewer='gpt-6.1-sol',reasoning_effort='low'),**changes}

    def test_full_coverage_required(self):
        with self.assertRaises(ValueError):decisions_for([{'id':'a'},{'id':'b'}],[self.decision()])

    def test_duplicate_decision_rejected(self):
        with self.assertRaises(ValueError):decisions_for([{'id':'a'}],[self.decision(),self.decision()])

    def test_quoted_and_none_retained(self):
        for label,kind in [('quoted','quoted'),('none','generic_howto')]:
            d=self.decision(label=label,kind=kind)
            self.assertEqual(decisions_for([{'id':'a'}],[d])['a'],d)

    def test_invalid_kind_rejected(self):
        with self.assertRaises(ValueError):decisions_for([{'id':'a'}],[self.decision(kind='reference')])
