"""Direct prompt-injection cues in the user's own (non-quoted) message text.

Three cue families are recognised on the detection view (NFKC, homoglyph and
zero-width normalisation, casefold): context hijacking, role impersonation and
privilege-escalation claims. A message that carries any cue no longer serves as
the authority anchor; the kernel ingests it as an untrusted USER_INJECTED source.
Patterns describe what is said to the agent, never whether a task is benign, so
an ordinary persona ("you are a technical writer") or an ops step ("run as
administrator") is not a cue.
"""
import re

from d2core.extractor import HOMOGLYPHS
from .normalization import normalize, GREEK

CATEGORY_LABEL = {'context_hijack': '上下文劫持', 'role_impersonation': '角色伪装',
                  'privilege_escalation': '越权声明'}


def _view(pattern):
    # Russian patterns must survive the same Cyrillic→Latin homoglyph folding as the text.
    return pattern.translate(HOMOGLYPHS).translate(GREEK)


ZH_PRIOR = r'(?:之前|此前|先前|以前|以上|上面|上述|前面|前述|原有|原来|原先|原本|已有|系统|所有|全部|一切|任何)'
ZH_RULES = r'(?:指令|指示|命令|规则|提示词|提示|设定|约束|限制|要求|安全策略|安全规则|安全限制|策略|系统提示|上下文|对话)'
EN_PRIOR = r'(?:previous|prior|preceding|above|earlier|former|original|system|developer)'
EN_RULES = (r'(?:instructions?|prompts?|rules?|directions?|directives?|context|guidelines?|messages?|constraints?'
            r'|guardrails?|restrictions?|safety\s+polic(?:y|ies)|security\s+polic(?:y|ies))')
NOT_UI = r'(?!\s*(?:panel|page|console|module|account|interface|dashboard|api|role|tool|view|guide|docs?|user)\b)'
UNRESTRICTED_ZH = (r'(?:开发者模式|越狱模式|越狱版|越狱|dan|上帝模式|特权模式|无限制模式|无限制|不受限制|不受任何限制|不受约束'
                   r'|没有任何限制|没有限制|无审查|不受审查|无过滤)')
UNRESTRICTED_EN = (r'(?:dan|jailbroken|jailbreak\s+mode|developer\s+mode|god\s+mode|admin\s+mode|sudo\s+mode|root\s+mode'
                   r'|unrestricted|unfiltered|uncensored|without\s+(?:any\s+)?(?:restrictions|limits|rules)|no\s+restrictions)')

RULES = {
    'context_hijack': [
        rf'(?:忽略|无视|忽视|忘记|忘掉|丢弃|抛开|抛弃|不要理会|不要遵守|不再遵守|停止遵守|推翻)\s*(?:掉|了)?\s*(?:你|您)?\s*{ZH_PRIOR}\s*'
        rf'(?:的|收到的|给你的|所有的|全部的)?\s*(?:所有|全部|任何|一切)?\s*的?\s*{ZH_RULES}',
        r'(?:之前|此前|先前|以上|上面|上述|前面|原有|原来)\s*的?\s*(?:所有|全部|一切)?\s*(?:指令|指示|规则|提示词|设定|约束|限制|安全策略|系统提示)'
        r'\s*(?:全部|都|均|一律|已经|已)?\s*(?:作废|失效|无效|不再适用|不再有效|被取消|取消|解除)',
        r'(?:最高优先级|更高优先级|优先级最高)\s*的?\s*(?:系统)?\s*(?:指令|指示|命令)|优先于\s*(?:之前|以上|系统)\s*的?\s*(?:所有)?\s*(?:指令|规则|设定)',
        r'(?:从现在起|从现在开始|接下来|此后)\s*[,，]?\s*(?:你)?\s*(?:不再|不用再|无需再|不必再)\s*(?:遵守|遵循|受|考虑)\s*(?:任何)?\s*'
        r'(?:之前的|原有的|系统的|安全)?\s*(?:规则|限制|约束|策略|指令|设定)',
        rf'\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+|every\s+)?(?:of\s+)?(?:the\s+|your\s+|these\s+|those\s+)?'
        rf'{EN_PRIOR}\s+(?:[a-z-]+\s+){{0,2}}?{EN_RULES}\b',
        r'\b(?:all\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|rules?|prompts?|directives?)\s+(?:are|is)\s+(?:now\s+)?'
        r'(?:void|cancell?ed|revoked|obsolete|invalid|null|no\s+longer\s+(?:valid|apply|applicable|in\s+effect))',
        r'\b(?:highest|top|higher)[- ]priority\s+(?:system\s+)?(?:instructions?|override|directive)\b'
        r'|\btakes?\s+precedence\s+over\s+(?:all\s+|any\s+)?(?:previous|prior|system|above)\b',
        r'\bfrom\s+now\s+on,?\s+(?:you\s+)?(?:will\s+|must\s+|should\s+)?(?:no\s+longer|not)\s+(?:follow|obey|comply|apply|be\s+bound)',
        r'\bend\s+of\s+(?:the\s+)?(?:system\s+prompt|user\s+(?:input|message|instructions?)|instructions)\b',
        r'(?:以前|前|上記|これまで|先ほど|先程|今まで)\s*の\s*(?:すべての|全ての|全)?\s*(?:指示|命令|ルール|プロンプト|設定|制約)\s*(?:を|は)\s*'
        r'(?:すべて|全て)?\s*(?:無視|忘れ|破棄|取り消|無効)',
        r'(?:指示|命令|ルール)\s*を\s*無視して',
        _view(r'(?:игнорируй|проигнорируй|игнорировать|забудь|забыть|отмени|не обращай внимания на)\s+(?:все\s+|всё\s+)?'
              r'(?:предыдущие|прежние|вышеуказанные|вышеприведённые|предшествующие|ранее данные|системные|исходные)\s+(?:\w+\s+)?'
              r'(?:инструкции|указания|правила|команды|ограничения|подсказки|промпты)'),
    ],
    'role_impersonation': [
        r'(?m)^[ \t]*(?:#{1,6}\s*)?(?:[\[【<(（]\s*/?\s*(?:system|sys|系统|系统消息|系统提示|系统指令|系统管理员|超级管理员|安全团队|developer|开发者|admin|administrator|管理员|root|operator|assistant|助手)'
        r'\s*[\]】>)）]|(?:system|developer|assistant|admin|administrator)\s*(?:message|prompt|instructions?|note|override)?\s*[:：]'
        r'|(?:系统消息|系统提示|系统指令|系统通知|管理员指令|管理员消息|管理员通知|开发者指令|开发者消息|运维指令|安全团队通知)\s*[:：])',
        r'<\|(?:im_start|im_end|system|assistant|user|start_header_id|end_header_id|eot_id|endoftext)\|>|\[/?inst\]|<</?sys>>',
        rf'(?:你|您)\s*(?:现在|从现在起|从现在开始|此后|接下来|已经)?\s*(?:是|扮演|充当|切换为|切换到|进入|成为|作为)\s*(?:一个|一名|一位)?\s*'
        rf'[^\n。！？,，]{{0,12}}?{UNRESTRICTED_ZH}',
        rf'(?:请你?|假装你?|假设你)\s*(?:扮演|充当|是|进入)\s*(?:一个|一名|一位)?\s*[^\n。！？,，]{{0,12}}?{UNRESTRICTED_ZH}',
        rf'\b(?:you\s+are\s+now|youre\s+now|from\s+now\s+on,?\s+you\s+are|act\s+as|pretend\s+(?:to\s+be|you\s+are)|roleplay\s+as)\s+'
        rf'(?:a\s+|an\s+|the\s+|in\s+)?(?:[\w-]+\s+){{0,3}}?{UNRESTRICTED_EN}\b',
        r'(?:我是|本人是|此消息来自|这是来自|以下(?:内容|指令|消息)?来自)\s*(?:你的|本系统的|系统的|平台的)?\s*'
        r'(?:系统管理员|超级管理员|管理员|安全团队|安全管理员|运维负责人|你的开发者|系统开发者|平台方|openai|anthropic)',
        rf'\b(?:i\s+am|im|this\s+is)\s+(?:the|your)\s+(?:system\s+administrator|administrator|admin|sysadmin|system\s+owner|operator|developer){NOT_UI}\b'
        rf'|\bthis\s+is\s+your\s+(?:system|security\s+team){NOT_UI}\b'
        rf'|\bmessage\s+from\s+(?:the|your)\s+(?:system|administrator|admin|security\s+team|developers?){NOT_UI}\b',
        r'(?:私は|こちらは)\s*(?:システム)?\s*管理者|(?:あなたは今|今からあなたは|これからあなたは)\s*.{0,10}?(?:開発者モード|制限のない|無制限|脱獄)',
        _view(r'\bя\s+(?:—\s+)?(?:ваш\s+|твой\s+)?(?:системный\s+)?администратор|(?:теперь\s+ты|ты\s+теперь)\s+(?:\S+\s+){0,2}?'
              r'(?:без\s+ограничений|в\s+режиме\s+разработчика|dan)'),
    ],
    'privilege_escalation': [
        r'(?:已|已经|业已)\s*(?:获得|获取|取得|拿到|被授予|被赋予|得到|通过)\s*了?\s*(?:用户|管理员|最高|系统|上级|安全团队|官方)?\s*的?\s*'
        r'(?:授权|许可|批准|审批|特许|管理员权限|最高权限|root\s*权限|超级权限)(?!\s*的)',
        r'(?:你|您)\s*(?:现在|已|已经)?\s*(?:拥有|具有|获得|被授予|有)\s*了?\s*(?:管理员|最高|root|超级用户|系统级|完全|无限制的?)\s*的?\s*(?:权限|访问权|控制权)',
        r'(?:赋予|授予)\s*(?:你|您)\s*(?:管理员|最高|root|超级用户|系统级|完全|全部)\s*的?\s*(?:权限|访问权|控制权)',
        r'(?:跳过|绕过|关闭|禁用|停用|关掉|解除|无视|忽略|规避)\s*(?:所有|全部|任何|一切)?\s*的?\s*(?:安全|防护)\s*'
        r'(?:确认|审批|审核|检查|校验|策略|限制|规则|机制|防护|拦截)',
        r'(?:跳过|绕过|关闭|禁用|停用|关掉|规避)\s*(?:所有|全部|任何|一切)?\s*的?\s*(?:人工确认|人工审核|人工审批|用户确认|审批|防护|防御|护栏|拦截|guard|d2guard|双镜)',
        r'(?:无需|不需要|不必|不用)\s*(?:经过|经|再)?\s*(?:用户|人工)\s*(?:确认|审批|批准|审核)|(?:无需|不需要|不必|不用)\s*(?:再)?\s*(?:审批|批准)',
        r'(?:自动批准|自动放行|一律放行|全部放行|直接放行)\s*(?:所有|全部|本次|此次|后续|接下来|以下)?\s*的?\s*(?:操作|调用|请求|命令|工具|动作)',
        r'\byou\s+(?:are|have\s+been)\s+(?:now\s+|hereby\s+|already\s+|fully\s+)?(?:granted|given)\s+(?:full\s+)?'
        r'(?:admin(?:istrator)?|root|elevated|sudo|superuser|unrestricted)\s+(?:privileges?|rights|permissions?|access)\b'
        r'|\byou\s+(?:now\s+)?(?:have|hold|possess)\s+(?:full\s+)?(?:admin(?:istrator)?|root|elevated|superuser|unrestricted)\s+'
        r'(?:privileges?|rights|permissions?|access)\b|\bi\s+(?:grant|give)\s+you\s+(?:full\s+)?(?:admin(?:istrator)?|root|elevated|superuser|unrestricted)\s+'
        r'(?:privileges?|rights|permissions?|access)\b',
        r'\b(?:skip|bypass|disable|turn\s+off|switch\s+off|circumvent|deactivate|suspend)\s+(?:all\s+|any\s+|the\s+|your\s+|every\s+)?'
        r'(?:(?:security|safety)\s+(?:checks?|confirmations?|approvals?|reviews?|guards?|guardrails?|filters?|policies|policy|restrictions?|measures?|mechanisms?|protections?|layers?)'
        r'|approvals?|guardrails?|d2guard|guard\b|human\s+review|manual\s+(?:review|approval))',
        r'\bno\s+(?:user\s+|human\s+|manual\s+)?(?:approval|authori[sz]ation)\s+(?:is\s+)?(?:needed|required|necessary)\b',
        r'\bauto-?approv(?:e|ed)\s+(?:all|every|any|each)\b'
        r'|\b(?:this|these|the\s+following|all)\s+(?:actions?|operations?|commands?|requests?|calls?|tools?)\s+(?:are|is|have\s+been|has\s+been)\s+'
        r'(?:pre-?approved|pre-?authori[sz]ed|already\s+approved)',
        r'\bauthori[sz]ation\s+(?:has\s+been\s+|was\s+|is\s+)(?:granted|approved|confirmed)\b'
        r'|\b(?:approved|authori[sz]ed)\s+by\s+(?:the\s+)?(?:admin(?:istrator)?|security\s+team|system\s+owner|it\s+department|management|ciso|root)\b',
        r'(?:承認|確認|許可)\s*(?:は)?\s*(?:不要|必要ありません|いりません)|(?:セキュリティ|安全)\s*(?:チェック|確認|制限|機能)?\s*を\s*(?:無効|スキップ|回避|解除|オフ)'
        r'|管理者権限\s*(?:が|を)\s*(?:付与|与え)|(?:すでに|既に)\s*(?:承認|許可)\s*(?:済み|されています)',
        _view(r'(?:без|не нужно|не требуется)\s+(?:какого-либо\s+)?(?:подтверждения|одобрения|согласования|разрешения)'
              r'|(?:отключи|обойди|отключить|обойти|пропусти)\s+(?:все\s+)?(?:защиту|проверки|проверку|безопасность|ограничения)'
              r'|(?:права|привилегии)\s+администратора|(?:уже\s+)?(?:одобрено|разрешено|санкционировано)\s+администратором'),
    ],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RULES.items()}
SENTENCE_END = re.compile(r'[。！？!?\n]|\.(?=\s|$)')


def _sentence(raw, a, b):
    start = max((m.end() for m in SENTENCE_END.finditer(raw, 0, a)), default=0)
    end = SENTENCE_END.search(raw, b)
    end = end.end() if end else len(raw)
    while start < end and raw[start].isspace():
        start += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    return [start, end]


def detect_direct_injection(trusted):
    """Return None, or the cue categories and raw character spans in ``trusted``."""
    if not trusted or not trusted.strip():
        return None
    text, mapping = normalize(trusted, casefold=True)
    matches = []
    for category, patterns in COMPILED.items():
        for pattern in patterns:
            for m in pattern.finditer(text):
                spans = mapping.char_to_raw[m.start():m.end()]
                if not spans:
                    continue
                a, b = min(s[0] for s in spans), max(s[1] for s in spans)
                if not trusted[a:b].strip():
                    continue
                matches.append({'category': category, 'label': CATEGORY_LABEL[category],
                                'cue': trusted[a:b], 'cue_span': [a, b], 'char_span': _sentence(trusted, a, b)})
                if len(matches) >= 16:
                    break
    if not matches:
        return None
    matches.sort(key=lambda x: x['cue_span'])
    categories = [c for c in CATEGORY_LABEL if any(x['category'] == c for x in matches)]
    return {'detected': True, 'categories': categories, 'labels': [CATEGORY_LABEL[c] for c in categories],
            'matches': matches[:16], 'signal': 'rule:DIRECT_INJECTION'}
