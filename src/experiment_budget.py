"""Optional host experiment limits; an absent value means unlimited."""
import os

def positive_limit(value):
    if value in (None, ''): return None
    number = int(value)
    if isinstance(value, bool) or number <= 0: raise ValueError('Limit must be a positive integer')
    return number

def environment_limits(env=None):
    env = os.environ if env is None else env
    return {key: positive_limit(env.get(name)) for key, name in
            [('model_requests', 'D2_MODEL_REQUEST_LIMIT'), ('tool_calls', 'D2_TOOL_CALL_LIMIT'),
             ('wall_seconds', 'D2_WALL_SECONDS')]}
