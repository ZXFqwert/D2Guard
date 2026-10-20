import unittest

from lab import pi_model_config


class ReasoningConfigurationTests(unittest.TestCase):
    def test_reasoning_capability_is_explicit(self):
        model = pi_model_config({'main_model': 'test', 'reasoning_capable': True}, 8192)
        self.assertTrue(model['reasoning'])
        self.assertEqual(model['maxTokens'], 8192)

    def test_existing_non_reasoning_provider_remains_compatible(self):
        self.assertFalse(pi_model_config({'main_model': 'test'}, 2048)['reasoning'])

    def test_string_false_cannot_enable_reasoning_protocol(self):
        self.assertFalse(pi_model_config({'main_model': 'test', 'reasoning_capable': 'false'}, 2048)['reasoning'])


if __name__ == '__main__':
    unittest.main()
