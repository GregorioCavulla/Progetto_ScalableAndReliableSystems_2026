#!/usr/bin/env python3

import argparse
import json
import os

import requests
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are RemediationAgent. Use bounded, reversible actions first. "
    "Always validate actions before execution. "
    "High-impact actions (add_drone, abort_order, checkpoint_drop) require human approval request."
)


class OpsClient:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def call(self, name: str, args: dict | None = None) -> dict:
        headers = {}
        if self.token:
            headers["X-MCP-Token"] = self.token
        payload = {"name": name, "args": args or {}}
        resp = requests.post(f"{self.base_url}/tool", json=payload, headers=headers, timeout=10)
        return resp.json().get("result", {})


class RemediationAgent:
    def __init__(
        self,
        ops_client: OpsClient,
        model: str,
        max_steps: int,
        temperature: float,
        model_name_for_cost: str,
    ):
        self.ops_client = ops_client
        self.model = model
        self.max_steps = max_steps
        self.temperature = temperature
        self.model_name_for_cost = model_name_for_cost
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        )

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "validate_action",
                    "description": "Validate action against safety policy before execution.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "args": {"type": "object"},
                            "source": {"type": "string"},
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "assign_order",
                    "description": "Assign order to a drone after validation.",
                    "parameters": {
                        "type": "object",
                        "properties": {"drone_id": {"type": "string"}, "order_id": {"type": "string"}},
                        "required": ["drone_id", "order_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_to_charge",
                    "description": "Charge drone with low battery.",
                    "parameters": {
                        "type": "object",
                        "properties": {"drone_id": {"type": "string"}},
                        "required": ["drone_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_to_repair",
                    "description": "Repair drone with low wear.",
                    "parameters": {
                        "type": "object",
                        "properties": {"drone_id": {"type": "string"}},
                        "required": ["drone_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "request_human_approval",
                    "description": "Open a human approval request for high-impact actions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string"},
                            "payload": {"type": "object"},
                            "reason": {"type": "string"},
                            "source": {"type": "string"},
                        },
                        "required": ["kind", "payload", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_pending_approvals",
                    "description": "Read pending human approvals.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "estimate_agent_cost",
                    "description": "Estimate run cost and compare with budget ceiling.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "step_count": {"type": "integer"},
                            "model_name": {"type": "string"},
                        },
                        "required": ["step_count", "model_name"],
                    },
                },
            },
        ]

    def run_once(self, observer_summary: str) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Observer summary: " + observer_summary + "\n"
                    "Plan bounded remediation actions. If uncertain or high impact, request human approval."
                ),
            },
        ]

        trace = []
        final_text = "remediation_no_decision"
        step_counter = 0

        for _ in range(self.max_steps):
            step_counter += 1

            budget = self.ops_client.call(
                "estimate_agent_cost",
                {"step_count": step_counter, "model_name": self.model_name_for_cost},
            )
            trace.append({"tool": "estimate_agent_cost", "args": {"step_count": step_counter}, "result": budget})
            if not budget.get("within_budget", True):
                final_text = "Budget ceiling reached, escalating to human"
                break

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
                    args = {}
                    if tc.function.arguments:
                        try:
                            parsed = json.loads(tc.function.arguments)
                            if isinstance(parsed, dict):
                                args = parsed
                        except json.JSONDecodeError:
                            args = {}
                    result = self.ops_client.call(tc.function.name, args)
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

            final_text = (msg.content or "remediation_no_decision").strip()
            break

        return {
            "remediation_summary": final_text,
            "remediation_tool_trace": trace,
            "steps_executed": step_counter,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RemediationAgent")
    parser.add_argument("--ops-url", default="http://127.0.0.1:8102", help="Operations MCP server URL")
    parser.add_argument("--ops-token", default=os.getenv("MCP_OPS_TOKEN", ""), help="Operations MCP token")
    parser.add_argument("--observer-summary", default="No observer summary provided", help="Observer summary")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="LLM model")
    parser.add_argument("--max-steps", type=int, default=4, help="Max tool-calling steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = RemediationAgent(
        ops_client=OpsClient(args.ops_url, token=args.ops_token),
        model=args.model,
        max_steps=args.max_steps,
        temperature=args.temperature,
        model_name_for_cost=args.model,
    )
    print(json.dumps(agent.run_once(args.observer_summary), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
