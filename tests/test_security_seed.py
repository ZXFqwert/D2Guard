import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_security_seed import rows


class SeedContracts(unittest.TestCase):
    def test_counterfactuals_and_language_variants_never_cross_family_split(self):
        data=list(rows());families={}
        for r in data:families.setdefault(r['family'],set()).add(r['split'])
        self.assertTrue(all(len(v)==1 for v in families.values()))
        self.assertEqual(len(data),384)
        groups={}
        for r in data:groups.setdefault(r['group_id'],[]).append(r)
        for group in groups.values():
            self.assertEqual({(r['gold']['explicit_authorization'],r['gold']['source_stance']) for r in group},
                             {(a,s) for a in (False,True) for s in ('requested','negated','quoted','informational')})

    def test_authorization_view_has_no_answer_flag_and_rows_are_not_real_runs(self):
        for r in rows():
            self.assertNotIn('in_user_granted_scope',r['compressed_payload']['security_delta'])
            self.assertNotIn('gold',r['compressed_payload'])
            self.assertFalse(r['training_ready'])
            self.assertEqual(r['provenance'],'synthetic_contract_not_agent_run')
            self.assertFalse(r['gold']['source_relation_is_proven_causal'])
