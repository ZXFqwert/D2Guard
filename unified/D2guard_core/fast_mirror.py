"""Compatibility entry point backed by the production adapter; no fabricated latency."""
from mirrors import FastMirrorAdapter


class FastMirror:
    def __init__(self):
        self.adapter = FastMirrorAdapter()

    def evaluate(self, normalized_text, current_plan, tool_name, tool_args):
        return self.adapter.classify(normalized_text + " " + str(tool_args), current_plan)
