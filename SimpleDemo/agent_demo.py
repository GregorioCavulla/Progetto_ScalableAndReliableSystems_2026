#!/usr/bin/env python3

import argparse
import json
import os
from typing import Any

from openai import OpenAI

from mcp_layer import SimpleMCP, load_events_from_jsonl


SYSTEM_PROMPT = (
    "You are an operations agent. Use only the provided tools. "
    "First inspect health, then decide. "
    "Do not run remediation when health is healthy. "
    "If uncertain, return final decision escalate_to_human."
)


class LLMAgent:
    """Tool-calling agent that uses an OpenAI-compatible endpoint (e.g. Ollama)."""

    def __init__(self, mcp: SimpleMCP, model: str, max_steps: int, temperature: float):
        self.mcp = mcp
        self.model = model
        self.max_steps = max_steps
        self.temperature = temperature
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        )

        self.tool_registry = {
            "get_system_status": self.mcp.get_system_status,
            "get_recent_events": self.mcp.get_recent_events,
            "run_remediation": self.mcp.run_remediation,
        }

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_system_status",
                    "description": "Get aggregate health status from recent events.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "window": {
                                "type": "integer",
                                "description": "Number of most recent events to analyze.",
                                "default": 20,
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recent_events",
                    "description": "Get recent events, optionally filtered by state.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "How many recent events to return.",
                                "default": 5,
                            },
                            "state": {
                                "type": "string",
                                "description": "Optional state filter: ok, warning, error.",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_remediation",
                    "description": "Execute a simulated remediation action.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def _safe_json_loads(self, raw_args: str | None) -> dict[str, Any]:
        if not raw_args:
            return {}
        try:
            parsed = json.loads(raw_args)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.tool_registry:
            return {"error": f"Tool '{name}' not allowed"}

        # Guardrail: prevent simulated remediation when system is healthy.
        if name == "run_remediation":
            status = self.mcp.get_system_status(window=20)
            if status.get("health") == "healthy":
                return {
                    "action": "blocked_by_policy",
                    "reason": "Remediation is not allowed when health is healthy",
                }

        try:
            return self.tool_registry[name](**args)
        except TypeError as exc:
            return {"error": f"Invalid arguments for {name}: {str(exc)}"}

    def run_once(self):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze current logs and decide next operational action. "
                    "You can inspect telemetry and optionally apply remediation."
                ),
            },
        ]

        audit_trace = []
        final_text = "escalate_to_human"

        for _ in range(self.max_steps):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=self.temperature,
            )

            msg = response.choices[0].message
            assistant_msg = {
                "role": "assistant",
                "content": msg.content or "",
            }

            if getattr(msg, "tool_calls", None):
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
                messages.append(assistant_msg)

                for tool_call in msg.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = self._safe_json_loads(tool_call.function.arguments)
                    tool_result = self._execute_tool(tool_name, tool_args)

                    audit_trace.append(
                        {
                            "tool": tool_name,
                            "args": tool_args,
                            "result": tool_result,
                        }
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": json.dumps(tool_result, ensure_ascii=True),
                        }
                    )
                continue

            final_text = (msg.content or "escalate_to_human").strip()
            messages.append(assistant_msg)
            break

        return {
            "status": self.mcp.get_system_status(window=20),
            "recent_errors": self.mcp.get_recent_events(limit=5, state="error"),
            "final_decision_text": final_text,
            "tool_trace": audit_trace,
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Run an Ollama-based tool-calling agent on streamed JSON logs")
    parser.add_argument("--events-file", required=True, help="Path to JSONL events file")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="Model name served by Ollama")
    parser.add_argument("--max-steps", type=int, default=3, help="Maximum LLM tool-calling steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    return parser.parse_args()


def main():
    args = parse_args()
    events = load_events_from_jsonl(args.events_file)

    mcp = SimpleMCP(events)
    agent = LLMAgent(mcp, model=args.model, max_steps=args.max_steps, temperature=args.temperature)
    result = agent.run_once()

    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
