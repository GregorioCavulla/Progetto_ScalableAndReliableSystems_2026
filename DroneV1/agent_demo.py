#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path

from observer_agent import ObservabilityClient, ObserverAgent
from remediation_agent import OpsClient, RemediationAgent


def run_coordinator(args: argparse.Namespace) -> dict:
    observer = ObserverAgent(
        obs_client=ObservabilityClient(args.obs_url),
        model=args.model,
        max_steps=args.observer_steps,
        temperature=args.temperature,
    )
    observer_result = observer.run_once()

    remediation = RemediationAgent(
        ops_client=OpsClient(args.ops_url, token=args.ops_token),
        model=args.model,
        max_steps=args.remediation_steps,
        temperature=args.temperature,
        model_name_for_cost=args.model,
    )
    remediation_result = remediation.run_once(observer_result.get("observer_summary", ""))

    result = {
        "observer": observer_result,
        "remediation": remediation_result,
    }

    if args.data_dir:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "last_observer_run.json").write_text(
            json.dumps(observer_result, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        (data_dir / "last_remediation_run.json").write_text(
            json.dumps(remediation_result, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        (data_dir / "last_agent_run.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8"
        )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DroneV1 multi-role agent coordinator")
    parser.add_argument("--obs-url", default="http://127.0.0.1:8101", help="Observability MCP URL")
    parser.add_argument("--ops-url", default="http://127.0.0.1:8102", help="Operations MCP URL")
    parser.add_argument("--ops-token", default=os.getenv("MCP_OPS_TOKEN", ""), help="Operations MCP token")
    parser.add_argument("--model", default="qwen2.5:7b-instruct", help="LLM model")
    parser.add_argument("--observer-steps", type=int, default=3, help="Observer max steps")
    parser.add_argument("--remediation-steps", type=int, default=4, help="Remediation max steps")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--data-dir", default="data", help="Directory for writing latest run artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(run_coordinator(args), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
