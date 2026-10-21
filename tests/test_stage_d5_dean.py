import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
import stage_d5_dean_finalize as d

class DeanAdmissionTests(unittest.TestCase):
    def test_direct_decision_overrides_old_contract_without_erasing_votes(self):
        row={'id':'a','label':'request','contract_label':'request'}
        decision={'id':'a','label':'none','kind':'reference','reason':'Historical completed action','reviewer':'gpt-6.1-sol','reasoning_effort':'low'}
        votes=[{'model':'deepseek-v4.1-flash','label':'request','kind':'concrete_task'}]
        result=d.adjudicated_row(row,decision,votes)
        self.assertEqual(result['label'],'none');self.assertEqual(result['original_label'],'request')
        self.assertEqual(result['original_teacher_votes'],votes);self.assertEqual(row['label'],'request')
    def test_qualified_reuse_is_not_claimed_as_direct_review(self):
        row={'id':'a','label':'request','contract_label':'request'}
        votes=[{'model':m,'label':'request','kind':'concrete_task'} for m in ('deepseek-flash','mimo-v2.5')]
        result=d.legacy_choice(row,votes)
        self.assertEqual(result['review_status'],'legacy_qualified_reused')
        self.assertNotIn('adjudication',result)
    def test_new_conflicting_vote_defers_old_consensus(self):
        row={'id':'a','label':'request','contract_label':'request'}
        votes=[{'model':m,'label':'request','kind':'concrete_task'} for m in ('deepseek-flash','mimo-v2.5')]
        votes.append({'model':'glm-5.3-flash','label':'none','kind':'reference'})
        self.assertIsNone(d.legacy_choice(row,votes))
    def test_duplicate_decisions_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r={'id':'a','label':'none','kind':'reference','reason':'Reference','reviewer':'gpt-6.1-sol','reasoning_effort':'low'}
            for name in ('a.jsonl','b.jsonl'):(root/name).write_text(json.dumps(r)+'\n')
            with patch.object(d,'OUT',root),patch.object(d,'DECISIONS',('a.jsonl','b.jsonl')):
                with self.assertRaises(ValueError):d.load_decisions()

if __name__=='__main__':unittest.main()
