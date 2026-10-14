"""Explicit live credential smoke test. Never prints credentials or runs during collection."""
import os
import pytest
from d2guard.llm_config import create_llm_client

@pytest.mark.live
@pytest.mark.skipif(os.getenv('D2GUARD_LIVE_TESTS')!='1',reason='Live model test requires explicit opt-in')
def test_model_connection():
    client,model=create_llm_client()
    assert client is not None,'Credentials unavailable'
    reply=client.chat.completions.create(model=model,messages=[{'role':'user','content':'Reply with OK'}],
                                         max_tokens=20,temperature=0)
    assert reply.choices[0].message.content
