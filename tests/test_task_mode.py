import unittest
from d2v2.compression import grant, action, literal_scope


class TaskModeTests(unittest.TestCase):
    def test_git_push_permission_matches_remote_and_ref(self):
        for task in ('Push HEAD:main to the local origin using git_push.',
                     'Run `git push origin HEAD:main`.', '推送 HEAD:main 到 origin。'):
            anchor=grant(task,{},0)
            args={'remote':'origin','ref':'HEAD:main'}
            self.assertTrue(literal_scope(action('git_push',args),args,anchor))
            for changed in ({'remote':'other','ref':'HEAD:main'},{'remote':'origin','ref':'HEAD:dev'}):
                self.assertFalse(literal_scope(action('git_push',changed),changed,anchor))
        anchor=grant('Do not push HEAD:main to origin.',{},0)
        self.assertFalse(literal_scope(action('git_push',args),args,anchor))

    def test_explicit_negation_does_not_forbid_authorized_release(self):
        for task in (
            'You are authorized to commit and push. This is a release task, not a read-only review.',
            '这不是只读审查，明确授权提交并推送代码。',
            'This is not a code review. Commit the release.',
        ):
            with self.subTest(task=task):
                self.assertEqual(grant(task, {}, 0)['intent_mode'], 'TASK')

    def test_actual_review_still_forbids_mutating_git(self):
        for task in ('Read-only code review.', 'Review the project code.', '审查项目代码。',
                     '只读审查代码，不要推送。', 'Do not disable read-only review.'):
            with self.subTest(task=task):
                self.assertEqual(grant(task, {}, 0)['intent_mode'], 'READONLY_REVIEW')


if __name__ == '__main__':
    unittest.main()
