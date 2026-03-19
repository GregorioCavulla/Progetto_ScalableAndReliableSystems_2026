#!/usr/bin/env python3

import argparse
import json
import random
import time
from datetime import datetime, timezone


SERVICES = ["ingest", "worker", "cache"]

STATE_MESSAGES = {
	"ok": ["heartbeat", "task completed", "resource stable"],
	"warning": ["high latency", "queue building", "retry triggered"],
	"error": ["service unavailable", "timeout", "unexpected exception"],
}

DRONE_SERVICES = ["order-streamer", "sales-agent", "drone-fleet", "fleet-agent", "custom-broker"]

DRONE_STATE_MESSAGES = {
	"ok": [
		"order accepted",
		"drone on route",
		"telemetry stable",
		"delivery confirmed",
	],
	"warning": [
		"battery below 30%",
		"queue backlog increasing",
		"wind impact detected",
		"route delay predicted",
	],
	"error": [
		"drone lost telemetry",
		"navigation timeout",
		"broker unavailable",
		"delivery failed",
	],
}


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def generate_generic_event() -> dict:
	service = random.choice(SERVICES)
	state = random.choices(["ok", "warning", "error"], weights=[70, 20, 10], k=1)[0]

	return {
		"timestamp": utc_now_iso(),
		"service": service,
		"state": state,
		"message": random.choice(STATE_MESSAGES[state]),
		"latency_ms": random.randint(20, 500),
	}


def generate_drone_event() -> dict:
	service = random.choice(DRONE_SERVICES)
	state = random.choices(["ok", "warning", "error"], weights=[64, 24, 12], k=1)[0]
	drone_id = f"DR-{random.randint(1, 12):02d}"
	order_id = f"ORD-{random.randint(1000, 9999)}"

	return {
		"timestamp": utc_now_iso(),
		"service": service,
		"state": state,
		"message": random.choice(DRONE_STATE_MESSAGES[state]),
		"latency_ms": random.randint(20, 600),
		"drone_id": drone_id,
		"order_id": order_id,
		"battery_pct": random.randint(10, 100),
	}


def stream_events(count: int, interval: float, profile: str) -> None:
	for _ in range(count):
		event = generate_drone_event() if profile == "drone" else generate_generic_event()
		print(json.dumps(event, ensure_ascii=True), flush=True)
		time.sleep(interval)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Simple JSON log streamer")
	parser.add_argument("--count", type=int, default=30, help="Number of events to emit")
	parser.add_argument("--interval", type=float, default=0.3, help="Seconds between events")
	parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
	parser.add_argument(
		"--profile",
		choices=["generic", "drone"],
		default="generic",
		help="Event profile: generic or project-domain drone logistics",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	if args.seed is not None:
		random.seed(args.seed)

	stream_events(count=args.count, interval=args.interval, profile=args.profile)


if __name__ == "__main__":
	main()
