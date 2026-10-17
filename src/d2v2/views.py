"""Question-specific textual views; facts and policy conclusions never cross here."""
import json

FORBIDDEN = {'in_user_granted_scope', 'matches_untrusted_taint', 'sensitive_target',
             'authorized', 'recent_steps'}


class InputBudgetExceeded(ValueError):
    pass


def encode_view(view):
    return json.dumps(view, ensure_ascii=False, sort_keys=True)


def check_fields(value):
    if isinstance(value, dict):
        if FORBIDDEN.intersection(value):
            raise ValueError('Computed answer fields in model view')
        for child in value.values():
            check_fields(child)
    elif isinstance(value, list):
        for child in value:
            check_fields(child)


def build_view(q, action, state):
    """state supplies text, a real tokenizer counter and relevant source excerpts.

    No truncation: the caller must ASK on budget failure. The eight-source window
    bounds presentation only; the decision queries the full persistent index.
    """
    description = f"{action['tool']} {action.get('op', '')} {action.get('target', '')}".strip()
    view = {'task': state['task_text'], 'action': description}
    if q == 'A2':
        view.update(external_sentences=state.get('directive_sentences', [])[:8],
                    agent_statement=state.get('agent_statement', ''))
    elif q != 'A1':
        raise ValueError('Unsupported action question')
    check_fields(view)
    if state['count_tokens'](encode_view(view)) > 320:
        raise InputBudgetExceeded('Question view exceeds 320 model tokens')
    return view
