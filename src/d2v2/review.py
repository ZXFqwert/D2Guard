from typing import Literal
from pydantic import BaseModel,ConfigDict,Field


class SlowAssessment(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    semantic_alignment: Literal['ALIGNED','DEVIANT_INJECTION','INSUFFICIENT']
    recommended_verdict: Literal['ALLOW','ASK','BLOCK']
    explainable_report_zh: str=Field(min_length=1,max_length=4000)
    supporting_event_ids: list[str]=Field(max_length=5)


def validate_assessment(value,allowed_ids):
    parsed=SlowAssessment.model_validate(value)
    if not set(parsed.supporting_event_ids)<=set(allowed_ids):
        raise ValueError('Unverifiable reviewer references')
    return parsed.model_dump()


class EvidenceCitation(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    event_id: str
    sha256: str
    char_span: list[int]=Field(min_length=2,max_length=2)

class CitedAssessment(SlowAssessment):
    citations: list[EvidenceCitation]=Field(min_length=1,max_length=5)

def validate_cited_assessment(value, snippets):
    parsed=CitedAssessment.model_validate(value).model_dump()
    allowed={(s['event_id'],s['sha256'],tuple(s['char_span'])) for s in snippets}
    cited={(s['event_id'],s['sha256'],tuple(s['char_span'])) for s in parsed['citations']}
    if not cited<=allowed or set(parsed['supporting_event_ids'])!={x[0] for x in cited}:
        raise ValueError('Reviewer references were not provided verbatim')
    return parsed

def fallback_assessment(pack):
    refs=[{k:s[k] for k in ('event_id','sha256','char_span')} for s in pack['snippets']]
    return {'semantic_alignment':'INSUFFICIENT','recommended_verdict':pack['local_verdict'],
            'explainable_report_zh': '用户任务与候选动作见所列证据。规则 '+pack['policy']+
                ' 已作出 '+pack['local_verdict']+'，调用未获执行许可。模型研判不可用，回退为确定性记录；未证实诱导因果。',
            'supporting_event_ids':list(dict.fromkeys(s['event_id'] for s in refs)), 'citations':refs}


def review_timeout_seconds(environ=None):
    """Host configuration, independent of Agent experiment budgets."""
    import os, math
    raw=(os.environ if environ is None else environ).get('D2_SLOW_REVIEW_TIMEOUT_SECONDS','90')
    value=float(raw)
    if not math.isfinite(value) or value<=0:
        raise ValueError('D2_SLOW_REVIEW_TIMEOUT_SECONDS must be finite and positive')
    return value
