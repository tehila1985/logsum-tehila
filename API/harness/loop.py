"""The agent loop: call the model while stop_reason == "tool_use"; all tool_results go back in ONE user message."""
from API.harness import caching, trace
from API.harness.history import to_param

MAX_ITERATIONS = 8


def run(client, request: dict, history, context, tools, tokens, max_iterations: int = MAX_ITERATIONS) -> dict:
    tool_calls = []
    text = ""
    for i in range(1, max_iterations + 1):
        system, schemas, messages = caching.apply(context.system(), tools.schemas(), context.messages(history))
        resp = client.beta.messages.create(**request, system=system, tools=schemas, messages=messages)
        tokens.record(resp.usage)
        history.append("assistant", [to_param(b) for b in resp.content])
        trace(__file__, f"call #{i} -> stop_reason={resp.stop_reason}")

        if resp.stop_reason == "refusal":
            text = "[the model declined this request]"
            break
        text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason != "tool_use":
            break

        uses = [b for b in resp.content if b.type == "tool_use"]
        tool_calls += [{"name": b.name, "input": b.input} for b in uses]
        results = [tools.run(b) for b in uses]
        history.append("user", results)  # one message with every tool_result
    else:
        trace(__file__, f"stopped after {max_iterations} iterations")
        text = text or "[stopped: too many tool iterations]"
    return {"text": text, "tool_calls": tool_calls}
