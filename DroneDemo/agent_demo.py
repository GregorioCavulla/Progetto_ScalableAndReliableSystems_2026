#!/usr/bin/env python3

import argparse
import json
import os
from typing import Any

from openai import OpenAI

from mcp_layer import DroneMCP, ensure_data_files

SYSTEM_PROMPT = (
    "You are a fleet operations AI agent. "
    "Use only provided tools. "
    "Prioritize urgent orders and safety. "
    "If considering add_drone, abort_order, or checkpoint_drop, request human approval."
)


class DroneLLMAgent:
    def __init__(self, mcp: DroneMCP, model: str, max_steps: int, temperature: float):
        self.mcp = mcp
        self.model = model
        self.max_steps = max_steps
        self.temperature = temperature
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        )

        self.tool_registry = {
            "get_fleet_snapshot": self.mcp.get_fleet_snapshot,
            "get_open_orders": self.mcp.get_open_orders,
            "estimate_order_cost": self.mcp.estimate_order_cost,
            "plan_dispatch": self.mcp.plan_dispatch,
            "assign_order": self.mcp.assign_order,
            "send_to_charge": self.mcp.send_to_charge,
            "send_to_repair": self.mcp.send_to_repair,
            "request_human_approval": self.mcp.request_human_approval,
            "list_pending_approvals": self.mcp.list_pending_approvals,
        }

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_fleet_snapshot",
                    "description": "Get latest fleet telemetry and health summary.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_open_orders",
                    "description": "List open queued/assigned orders sorted by urgency.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "default": 50}
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "estimate_order_cost",
                    "description": "Estimate distance and battery required for one order.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"}
                        },
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "plan_dispatch",
                    "description": "Create assignment suggestions and identify approvals needed.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "assign_order",
                    "description": "Assign an order to a suitable drone.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "drone_id": {"type": "string"},
                            "order_id": {"type": "string"},
                        },
                        "required": ["drone_id", "order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_to_charge",
                    "description": "Send a drone to charge cycle.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "drone_id": {"type": "string"}
                        },
                        "required": ["drone_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_to_repair",
                    "description": "Send a drone to repair cycle.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "drone_id": {"type": "string"}
                        },
                        "required": ["drone_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "request_human_approval",
                    "description": "Create human approval request for add_drone, abort_order, checkpoint_drop.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string"},
                            "payload": {"type": "object"},
                            "reason": {"type": "string"},
                        },
                        "required": ["kind", "payload", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_pending_approvals",
                    "description": "List currently pending human approvals.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def _safe_json(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = self.tool_registry.get(name)
        if fn is None:
            return {"error": f"Tool {name} not available"}
        try:
            result = fn(**args)
            if isinstance(result, dict):
                return result
            return {"result": result}
        except TypeError as exc:
            return {"error": f"Invalid args for {name}: {str(exc)}"}

    def run_once(self) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Analyze fleet and orders, then take useful actions. "
                    "Use human approval request when policy requires it."
                ),
            },
        ]

        trace = []
        final_text = "no_decision"

        for _ in range(self.max_steps):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=self.temperature,
            )
            msg = resp.choices[0].message

            assistant_msg = {"role": "assistant", "content": msg.content or ""}
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
                messages.append(assistant_msg)

                for tc in tool_calls:
                    args = self._safe_json(tc.function.arguments)
                    result = self._run_tool(tc.function.name, args)
                    trace.append({"tool": tc.function.name, "args": args, "result": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": json.dumps(result, ensure_ascii=True),
                        }
                    )
                continue

            final_text = (msg.content or "no_decision").strip()
            messages.append(assistant_msg)
            break

        return {
            "final_decision_text": final_text,
            "tool_trace": trace,
            "fleet": self.mcp.get_fleet_snapshot(),
            "orders": self.mcp.get_open_orders(limit=30),
            "pending_approvals": self.mcp.list_pending_approvals(),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DroneDemo LLM agent")
    parser.add_argument("--data-dir", default="data", help="Directory with demo JSONL files")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="Ollama model name")
    parser.add_argument("--max-steps", type=int, default=4, help="Maximum tool-calling rounds")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_data_files(args.data_dir)
    mcp = DroneMCP(args.data_dir)
    agent = DroneLLMAgent(mcp=mcp, model=args.model, max_steps=args.max_steps, temperature=args.temperature)
    result = agent.run_once()
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
