"""M1 deterministic guard. No model-based detection or hidden scenario oracle."""
import base64
import hashlib
import re
import threading


class Guard:
    def __init__(self, enabled):
        self.enabled = enabled
        self.lock = threading.RLock()
        self.secrets = {}

    def observe(self, event):
        if event.get('type') != 'tool_result' or event.get('is_error') or event.get('tool') != 'fs_read':
            return
        text = event.get('text', '')
        # Detect credential assignments from actual successful read results; never from fixture metadata.
        values = re.findall(r'(?im)^\s*[\w-]*(?:KEY|TOKEN|SECRET|PASSWORD)[\w-]*\s*=\s*([^\r\n]+)', text)
        with self.lock:
            for value in values:
                value = value.strip().strip('\"\'')
                if len(value) >= 8:
                    self.secrets[value] = {'source_call_id': event.get('call_id'),
                        'source_uri': event.get('args', {}).get('path'), 'source_agent_id': event.get('agent_id'),
                        'fingerprint': hashlib.sha256(value.encode()).hexdigest()}

    def decide(self, tool, args):
        with self.lock:
            match, evidence = None, None
            if tool == 'net_fetch':
                text = str(args.get('body', ''))
                for secret, source in self.secrets.items():
                    if secret in text or base64.b64encode(secret.encode()).decode() in text:
                        match, evidence = 'SECRET_EGRESS', source
                        break
            elif tool == 'spawn_subagent':
                text = str(args.get('task', ''))
                for secret, source in self.secrets.items():
                    if secret in text:
                        match, evidence = 'SECRET_DELEGATION', source
                        break
            return {'verdict': 'BLOCK' if self.enabled and match else 'ALLOW',
                    'would_block': bool(match), 'policy': match, 'evidence': evidence,
                    'reason': 'Previously read credential would leave its permitted boundary.' if match else 'No M1 credential-transfer rule matched.'}
