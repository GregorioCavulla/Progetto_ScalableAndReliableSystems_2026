#!/usr/bin/env python3

import argparse
import json
import random
import time
from pathlib import Path

from mcp_layer import BATTERY_PER_METER, MAX_ONE_WAY_METERS, WAREHOUSE, append_jsonl, ensure_data_files

STATUSES = ["landed", "takingoff", "routing", "flying", "landing", "arrived", "returning"]


def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def random_status(prev_status: str) -> str:
    transitions = {
        "landed": ["landed", "takingoff", "routing"],
        "takingoff": ["routing", "flying"],
        "routing": ["flying", "arrived", "returning"],
        "flying": ["flying", "arrived", "returning", "landing"],
        "landing": ["landed", "arrived"],
        "arrived": ["returning", "landing", "landed"],
        "returning": ["flying", "landing", "landed"],
    }
    return random.choice(transitions.get(prev_status, STATUSES))


def status_speed(status: str) -> float:
    if status in {"routing", "flying", "returning"}:
        return random.uniform(120.0, 420.0)
    if status in {"takingoff", "landing"}:
        return random.uniform(20.0, 90.0)
    return 0.0


def init_drones() -> list[dict]:
    drones = []
    for i in range(1, 5):
        drones.append(
            {
                "drone_id": f"D{i}",
                "status": "landed",
                "battery_pct": 100.0,
                "wear_pct": 100.0,
                "lon": WAREHOUSE[0],
                "lat": WAREHOUSE[1],
                "wind": 0.0,
                "assigned_order_id": None,
            }
        )
    return drones


def update_drone(drone: dict, interval: float) -> dict:
    status = random_status(drone["status"])
    wind = random.uniform(0.0, 25.0)
    meters = status_speed(status) * interval

    if status in {"routing", "flying", "returning"} and meters > 0:
        angle = random.uniform(0.0, 360.0)
        dx = meters * 0.7 * (1 if angle < 180 else -1)
        dy = meters * 0.7 * (1 if 90 < angle < 270 else -1)
        drone["lon"] = clamp(drone["lon"] + dx, -MAX_ONE_WAY_METERS, MAX_ONE_WAY_METERS)
        drone["lat"] = clamp(drone["lat"] + dy, -MAX_ONE_WAY_METERS, MAX_ONE_WAY_METERS)

    wind_factor = 1.0 + (wind / 100.0)
    battery_drop = meters * BATTERY_PER_METER * wind_factor
    wear_drop = (meters / 1000.0) * random.uniform(0.3, 1.3)

    drone["battery_pct"] = round(clamp(drone["battery_pct"] - battery_drop, 0.0, 100.0), 2)
    drone["wear_pct"] = round(clamp(drone["wear_pct"] - wear_drop, 0.0, 100.0), 2)
    drone["status"] = status
    drone["wind"] = round(wind, 2)

    if drone["status"] in {"landed", "arrived"} and drone["battery_pct"] < 20.0:
        drone["status"] = "landed"
        drone["lon"] = WAREHOUSE[0]
        drone["lat"] = WAREHOUSE[1]

    return drone


def stream(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    ensure_data_files(data_dir)
    events_file = data_dir / "drone_events.jsonl"

    drones = init_drones()
    for _ in range(args.ticks):
        ts = int(time.time())
        for drone in drones:
            updated = update_drone(drone, args.interval)
            event = {
                "timestamp": ts,
                "drone_id": updated["drone_id"],
                "status": updated["status"],
                "battery_pct": updated["battery_pct"],
                "wear_pct": updated["wear_pct"],
                "lon": round(updated["lon"], 2),
                "lat": round(updated["lat"], 2),
                "wind": updated["wind"],
                "assigned_order_id": updated["assigned_order_id"],
            }
            append_jsonl(events_file, event)
            if args.stdout:
                print(json.dumps(event, ensure_ascii=True), flush=True)

        time.sleep(args.interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate drone telemetry events")
    parser.add_argument("--data-dir", default="data", help="Directory for JSONL files")
    parser.add_argument("--ticks", type=int, default=60, help="Number of ticks")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds per tick")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    parser.add_argument("--stdout", action="store_true", help="Print events to stdout")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    stream(args)


if __name__ == "__main__":
    main()
