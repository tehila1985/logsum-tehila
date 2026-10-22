"""cache_control breakpoints. Order rendered by the API: tools -> system -> messages."""
from API.harness import trace

EPHEMERAL = {"type": "ephemeral"}


def apply(system: list[dict], tools: list[dict], messages: list[dict]):
    """Return request copies with 3 breakpoints: last tool, system, last message block.
    The stored history is not modified."""
    tools = [*tools[:-1], {**tools[-1], "cache_control": EPHEMERAL}] if tools else tools
    system = [*system[:-1], {**system[-1], "cache_control": EPHEMERAL}] if system else system
    if messages:
        last = messages[-1]
        content = last["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        content = [*content[:-1], {**content[-1], "cache_control": EPHEMERAL}]
        messages = [*messages[:-1], {**last, "content": content}]
    trace(__file__, "cache_control on: tools[-1], system[-1], messages[-1]")
    return system, tools, messages
