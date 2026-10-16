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
