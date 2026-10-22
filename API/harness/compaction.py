"""Summarize the whole conversation once the context passes a threshold (simple compaction:
the summary replaces all earlier messages in the request; nothing is deleted from disk)."""
from API.harness import trace

SUMMARY_REQUEST = (
    "Summarize our conversation so far for your own future use: decisions, saved memory changes, "
    "findings per log file (counts, times), and open questions. Be concise. "
    "Reply with the summary text only; do not call any tools."
)


class Compactor:
    def __init__(self, threshold_tokens: int):
        self.threshold = threshold_tokens

    def should_compact(self, last_input_total: int) -> bool:
        return last_input_total > self.threshold

    def compact(self, client, request: dict, system, tools, messages, history, tokens) -> None:
        trace(__file__, f"context {tokens.last_input_total} > {self.threshold} tokens: compacting")
        ask = {"role": "user", "content": [{"type": "text", "text": SUMMARY_REQUEST}]}
        # Same system + tools as the agent calls, so the cached prefix is reused.
        resp = client.beta.messages.create(**request, system=system, tools=tools, messages=[*messages, ask])
        tokens.record(resp.usage, purpose="compaction")
        summary = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        history.append_compaction(summary or "(empty summary)")
