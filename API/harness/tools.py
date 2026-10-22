"""Tool schemas, dispatch, and errors returned to the model as is_error."""
import copy
import json

from API.harness import trace
from shared.errors import ToolError
from shared.log_tools import TOOL_NAMES, Toolbox
from shared.schemas import TOOL_SPECS

MAX_RESULT_CHARS = 1500


class ToolRegistry:
    def __init__(self, toolbox: Toolbox, max_chars: int = MAX_RESULT_CHARS):
        self.handlers = {name: getattr(toolbox, name) for name in TOOL_NAMES}
        self.max_chars = max_chars
        self._schemas = copy.deepcopy(TOOL_SPECS)  # fixed order -> stable cache prefix

    def schemas(self) -> list[dict]:
        return self._schemas

    def run(self, block) -> dict:
        """Execute one tool_use block and return its tool_result block."""
        name, args = block.name, block.input or {}
        is_error = False
        try:
            if name not in self.handlers:
                raise ToolError(f"unknown tool '{name}'. available: {sorted(self.handlers)}")
            content = self.handlers[name](**args)
        except ToolError as e:
            content, is_error = f"error: {e}", True
        except TypeError as e:
            content, is_error = f"error: bad arguments for {name}: {e}", True
        except Exception as e:  # a bug in a tool must not kill the loop
            content, is_error = f"error: internal {type(e).__name__}: {e}", True
        if len(content) > self.max_chars:
            content = content[: self.max_chars] + '..."truncated":true'
        trace(__file__, f"dispatch {name}({json.dumps(args, ensure_ascii=False)}) -> "
                        f"{'ERROR ' if is_error else ''}{len(content)} chars")
        result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
        if is_error:
            result["is_error"] = True
        return result
