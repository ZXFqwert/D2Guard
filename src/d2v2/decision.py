"""Design §4.4, first matching row. No IO, model calls or mutable state.

Model answers must explicitly carry calibrated=True and threshold_passed=True.
Uncalibrated baseline probabilities (including NOUL) never grant authority.
Protocol/session/incomplete-input guards are separate from the semantic table.
"""


def answer(answers, question):
    value = answers.get(question, {})
    if value.get('calibrated') is True and value.get('threshold_passed') is True:
        return value.get('label', 'unclear')
    return 'unclear'


def required_questions(facts):
    if (facts.get('hard_policy') or facts.get('soft_policy') or facts.get('secret_hit') and facts.get('untrusted_sink')
            or facts.get('context_secret') and facts.get('untrusted_sink') and not facts.get('network_granted')
            or facts.get('literal_scope')
            or facts.get('direct_injection') and (facts.get('sensitive') or facts.get('high_risk'))
            or facts.get('sensitive') and facts.get('directive')):
        return ()
    if facts.get('sensitive') or facts.get('low_risk'):
        return ('A1',)
    if facts.get('decision_mode') in {'taint_gate','rules_gate'} and facts.get('high_risk'):
        return ()
    if facts.get('high_risk') and facts.get('tainted'):
        return ('A1', 'A2')
    return ()


def decide(facts, model_answers):
    """Return (verdict, rule_id, risk, reason); identifiers map to table rows."""
    if facts.get('hard_policy'):
        return 'BLOCK', facts['hard_policy'], 'R3', facts.get('hard_reason') or '命中硬策略（§4.4 第 1 条）。'
    if facts.get('secret_hit') and facts.get('untrusted_sink'):
        return 'BLOCK', 'DT-2a', 'R3', '参数命中机密指纹，禁止向不可信边界披露。'
    if facts.get('context_secret') and facts.get('untrusted_sink') and not facts.get('network_granted'):
        return 'ASK', 'DT-2b', 'R2', '上下文含机密，外发内容可能经过编码或分片，需要用户确认。'
    if facts.get('soft_policy'):
        return 'ASK', facts['soft_policy'], 'R2', facts.get('soft_reason') or '状态策略要求确认。'
    if facts.get('literal_scope'):
        return 'ALLOW', 'DT-3', 'R0', '动作在用户字面授权内，未命中机密外流条件。'
    if facts.get('direct_injection') and (facts.get('sensitive') or facts.get('high_risk')):
        return 'ASK', 'DT-4i', 'R2', '用户输入含直接注入特征（上下文劫持、角色伪装或越权声明），该消息不产生授权，敏感或高风险动作需人工确认。'
    if facts.get('sensitive') and facts.get('directive'):
        return 'ASK', 'DT-4a', 'R2', '未授权敏感动作命中外部指令索引；这是关联证据，不是因果证明。'
    a1, a2 = answer(model_answers, 'A1'), answer(model_answers, 'A2')
    if facts.get('sensitive'):
        if a1 == 'direct':
            return 'ALLOW', 'DT-4b', 'R1', 'A1 经校准确认动作是任务直接需要。'
        return 'ASK', 'DT-4b', 'R2', '未授权敏感动作缺少经校准的直接任务需要证据。'
    if facts.get('high_risk') and facts.get('tainted'):
        if facts.get('decision_mode') in {'taint_gate','rules_gate'}:
            if facts.get('request_tainted',True):
                return 'ASK','DT-4c','R2','上下文存在请求污染或未可靠覆盖的来源。'
            if facts.get('untrusted_sink'):
                return 'ASK','DT-4c-EGRESS','R2','未授权外发目标需要用户确认，即使上下文没有请求污染。'
            return 'ALLOW','DT-4c-S1' if facts['decision_mode']=='taint_gate' else 'DT-4c-RULE','R1','上下文来源未命中请求污染；保留完整integrity溯源。'
        if a2 == 'external' or a1 == 'unrelated':
            return 'ASK', 'DT-4c', 'R2', '经校准语义结果表明高风险动作偏离任务或由外部要求驱动。'
        if a1 in {'direct', 'ancillary'} and a2 == 'user':
            return 'ALLOW', 'DT-4c', 'R1', 'A1 与 A2 均经校准支持任务内动作。'
    if facts.get('low_risk') and a1 != 'unclear':
        if a1 == 'unrelated':
            return 'ASK', 'DT-4d', 'R1', 'A1 经校准判定该低风险动作与任务无关。'
        if a1 in {'direct', 'ancillary'}:
            return 'ALLOW', 'DT-4d', 'R0', 'A1 经校准支持低风险任务动作。'
    if facts.get('high_risk') and not facts.get('tainted'):
        return 'ALLOW', 'DT-4e', 'R1', '非敏感高风险动作的上下文未摄入不可信来源，允许并记录。'
    if facts.get('unknowns') and facts.get('high_risk'):
        return 'ASK', 'DT-5', 'R2', '高风险动作涉及尚未解析的外部指令。'
    if facts.get('low_risk'):
        return 'ALLOW', 'DT-6', 'R0', '语义结果 unclear；允许低风险动作并记录不确定性。'
    return 'ASK', 'DT-6', 'R2', '语义结果 unclear，不能确认高风险或未知动作。'
