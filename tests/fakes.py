"""A scripted stand-in for anthropic.Anthropic: no network, no key."""
from types import SimpleNamespace


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def thinking(sig: str = "sig"):
    return SimpleNamespace(type="thinking", thinking="", signature=sig)


def tool_use(id_: str, name: str, **inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def response(*blocks, stop="end_turn", inp=100, out=20, cache_r=0, cache_w=0):
    usage = SimpleNamespace(input_tokens=inp, output_tokens=out,
                            cache_read_input_tokens=cache_r, cache_creation_input_tokens=cache_w)
    return SimpleNamespace(content=list(blocks), stop_reason=stop, usage=usage)


class FakeClient:
    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.script:
            raise AssertionError("FakeClient: no scripted response left")
        return self.script.pop(0)
