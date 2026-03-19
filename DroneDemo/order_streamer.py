#!/usr/bin/env python3

import argparse
import random
import time
from pathlib import Path

from mcp_layer import append_jsonl, ensure_data_files

URGENCY = ["non_urgente", "normale", "prioritario"]


def stream_orders(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    ensure_data_files(data_dir)
    orders_file = data_dir / "orders.jsonl"

    for i in range(args.count):
        ts = int(time.time())
        order = {
            "timestamp": ts,
            "created_at": ts,
            "order_id": f"ORD-{ts}-{i}",
            "product": random.choice([1, 2, 3, 4]),
            "dest_lon": round(random.uniform(-10000.0, 10000.0), 2),
            "dest_lat": round(random.uniform(-10000.0, 10000.0), 2),
            "urgency": random.choices(URGENCY, weights=[35, 45, 20], k=1)[0],
            "status": "queued",
            "assigned_drone_id": None,
        }
        append_jsonl(orders_file, order)
        if args.stdout:
            print(order)
        time.sleep(args.interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate order events")
    parser.add_argument("--data-dir", default="data", help="Directory for JSONL files")
    parser.add_argument("--count", type=int, default=30, help="How many orders to create")
    parser.add_argument("--interval", type=float, default=0.3, help="Seconds between orders")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    parser.add_argument("--stdout", action="store_true", help="Print generated orders")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    stream_orders(args)


if __name__ == "__main__":
    main()
