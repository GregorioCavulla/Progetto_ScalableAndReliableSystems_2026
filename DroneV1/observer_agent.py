#!/usr/bin/env python3

import argparse
import json
import os

import requests
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are ObserverAgent. You can only inspect telemetry and propose actions. "
    "Do not execute operational changes. Return concise triage summary."
)


class ObservabilityClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def call(self, name: str, args: dict | None = None) -> dict:
        payload = {"name": name, "args": args or {}}
        resp = requests.post(f"{self.base_url}/tool", json=payload, timeout=10)
        return resp.json().get("result", {})


class ObserverAgent:
    def __init__(self, obs_client: ObservabilityClient, model: str, max_steps: int, temperature: float):
        self.obs_client = obs_client
        self.model = model
        self.max_steps = max_steps
        self.temperature = temperature
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        )

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_fleet_snapshot",
                    "description": "Read latest drone fleet status and health summary.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_open_orders",
                    "description": "Read currently open orders.",
                    "parameters": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer", "default": 30}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "plan_dispatch",
                    "description": "Get deterministic dispatch and approval suggestions.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_policy_limits",
                    "description": "Read policy guardrails and ceilings.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def run_once(self) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Inspect fleet and orders. Produce risk assessment and recommendations for RemediationAgent. "
                    "If uncertainty is high, recommend human escalation."
                ),
            },
        ]

        trace = []
        final_text = "observer_no_decision"

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
                    args = {}
                    if tc.function.arguments:
                        try:
                            parsed = json.loads(tc.function.arguments)
                            if isinstance(parsed, dict):
                                args = parsed
                        except json.JSONDecodeError:
                            args = {}
                    result = self.obs_client.call(tc.function.name, args)
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

            final_text = (msg.content or "observer_no_decision").strip()
            break

        return {
            "observer_summary": final_text,
            "observer_tool_trace": trace,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ObserverAgent")
    parser.add_argument("--obs-url", default="http://127.0.0.1:8101", help="Observability MCP server URL")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="LLM model")
    parser.add_argument("--max-steps", type=int, default=3, help="Max tool-calling steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent = ObserverAgent(
        obs_client=ObservabilityClient(args.obs_url),
        model=args.model,
        max_steps=args.max_steps,
        temperature=args.temperature,
    )
    print(json.dumps(agent.run_once(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
