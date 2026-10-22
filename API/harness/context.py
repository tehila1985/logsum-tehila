"""What goes into each request: frozen system prompt, active history, per-turn memory block."""
from API.harness import trace


class Context:
    def __init__(self, system_prompt: str):
        # Never edited during a session: a changed system prompt would break the cache
        # and invalidate earlier thinking blocks.
        self._system = [{"type": "text", "text": system_prompt}]

    def system(self) -> list[dict]:
        return self._system

    def user_message(self, text: str, memory_block: str) -> list[dict]:
        """Memory is sent inside the user turn (and stays in history), not in the system prompt."""
        return [{"type": "text", "text": memory_block}, {"type": "text", "text": text}]

    def messages(self, history) -> list[dict]:
        summary, msgs = history.active()
        if summary is not None and msgs:
            first = msgs[0]
            note = {"type": "text", "text": f"<summary_of_earlier_conversation>\n{summary}\n</summary_of_earlier_conversation>"}
            msgs = [{"role": "user", "content": [note, *first["content"]]}, *msgs[1:]]
        trace(__file__, f"{len(msgs)} messages in context" + (" (+ compaction summary)" if summary else ""))
        return msgs
