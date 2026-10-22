"""Diagnose the API harness setup step by step:  python tools/check_api.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

key = os.environ.get("ANTHROPIC_API_KEY", "")
if not key:
    sys.exit('1. FAIL: ANTHROPIC_API_KEY is not set in this terminal. Run:  $env:ANTHROPIC_API_KEY="sk-ant-..."')
print(f"1. OK: key is set ({key[:10]}..., {len(key)} chars)")
if not key.startswith("sk-ant-"):
    print("   WARNING: a Console API key normally starts with sk-ant-")

import anthropic  # noqa: E402

from shared.schemas import TOOL_SPECS  # noqa: E402

client = anthropic.Anthropic(api_key=key)
MODEL = "claude-opus-5-5"


def step(n, label, **kw):
    try:
        r = client.beta.messages.create(model=MODEL, max_tokens=200, messages=[{"role": "user", "content": "Say OK."}], **kw)
        print(f"{n}. OK: {label} (stop_reason={r.stop_reason})")
        return True
    except anthropic.AuthenticationError as e:
        print(f"{n}. FAIL: {label}: the key is invalid or revoked. Create a new one in console.anthropic.com\n   {e}")
    except anthropic.PermissionDeniedError as e:
        print(f"{n}. FAIL: {label}: this key has no access to {MODEL}\n   {e}")
    except anthropic.RateLimitError as e:
        print(f"{n}. FAIL: {label}: rate limited, wait a minute and retry\n   {e}")
    except anthropic.BadRequestError as e:
        msg = str(e)
        hint = "no credit on the account: add credits in console.anthropic.com > Billing" if "credit" in msg.lower() else "the request was rejected"
        print(f"{n}. FAIL: {label}: {hint}\n   {e}")
    except anthropic.APIConnectionError as e:
        print(f"{n}. FAIL: {label}: cannot reach api.anthropic.com (network/proxy/firewall)\n   {e}")
    except anthropic.APIStatusError as e:
        print(f"{n}. FAIL: {label}: HTTP {e.status_code}\n   {e}")
    return False


ok = step(2, "plain request")
ok = ok and step(3, "with effort=medium", output_config={"effort": "medium"})
ok = ok and step(4, "with server-side fallbacks", output_config={"effort": "medium"},
                 betas=["server-side-fallback-2026-07-01"], fallbacks="default")
if ok:
    tools = [*TOOL_SPECS[:-1], {**TOOL_SPECS[-1], "cache_control": {"type": "ephemeral"}}]
    ok = step(5, "with the LogSum tools + cache_control", output_config={"effort": "medium"}, tools=tools,
              system=[{"type": "text", "text": "test", "cache_control": {"type": "ephemeral"}}])
print("\nAll good: the API harness should work." if ok else
      "\nFix the first FAIL above. If step 4 failed and 2-3 passed, run the harness with --no-fallbacks.")
