"""Usage and cost per model call and per turn."""
from API.harness import trace

# $ per million tokens. cache_write = 1.25x input (5-minute TTL).
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "cache_write": 5.00, "cache_read": 0.20, "output": 20.00},
}


class TokenMeter:
    def __init__(self, model: str):
        self.price = PRICES[model]
        self.turn = self._empty()
        self.last_input_total = 0

    @staticmethod
    def _empty() -> dict:
        return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "model_calls": 0, "cost_usd": 0.0}

    def start_turn(self) -> None:
        self.turn = self._empty()

    def record(self, usage, purpose: str = "agent") -> None:
        call = {
            "input": usage.input_tokens or 0,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "output": usage.output_tokens or 0,
        }
        cost = sum(call[k] * self.price[k] for k in call) / 1_000_000
        for k, v in call.items():
            self.turn[k] += v
        self.turn["model_calls"] += 1
        self.turn["cost_usd"] += cost
        self.last_input_total = call["input"] + call["cache_read"] + call["cache_write"]
        trace(__file__, f"{purpose} call: in={call['input']} cache_r={call['cache_read']} "
                        f"cache_w={call['cache_write']} out={call['output']} ${cost:.4f}")

    def end_turn(self) -> dict:
        t = dict(self.turn)
        t["cost_usd"] = round(t["cost_usd"], 6)
        trace(__file__, f"turn total: calls={t['model_calls']} in={t['input']} cache_r={t['cache_read']} "
                        f"cache_w={t['cache_write']} out={t['output']} ${t['cost_usd']:.4f}")
        return t


def cache_pct(t: dict) -> float:
    total = t["input"] + t["cache_read"] + t["cache_write"]
    return round(100 * t["cache_read"] / total, 1) if total else 0.0
