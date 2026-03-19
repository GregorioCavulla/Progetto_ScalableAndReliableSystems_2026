#!/usr/bin/env python3

import argparse
import json
import random
import time
from pathlib import Path

from mcp_layer import (
    BATTERY_RESERVE,
    BATTERY_PER_METER,
    CHECKPOINTS,
    MAX_ONE_WAY_METERS,
    WAREHOUSE,
    append_jsonl,
    ensure_data_files,
    load_jsonl,
)

STATUSES = ["landed", "takingoff", "routing", "flying", "landing", "arrived", "returning"]
AIRBORNE_STATUSES = {"takingoff", "routing", "flying", "returning", "landing"}
CHARGING_STATUSES = {"landed", "arrived"}

CHARGE_RATE_PCT_PER_SEC = 8.0
CHECKPOINT_CHARGE_RADIUS = 220.0
ARRIVAL_RADIUS = 40.0

TAKEOFF_SECONDS = 2.0
LANDING_SECONDS = 2.0
ARRIVED_DWELL_SECONDS = 1.5

TAKEOFF_SPEED_MPS = 35.0
ROUTING_SPEED_MPS = 180.0
FLYING_SPEED_MPS = 260.0
RETURNING_SPEED_MPS = 240.0
LANDING_SPEED_MPS = 30.0


def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def distance(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    return ((b_lon - a_lon) ** 2 + (b_lat - a_lat) ** 2) ** 0.5


def move_towards(cur_lon: float, cur_lat: float, dst_lon: float, dst_lat: float, meters: float) -> tuple[float, float, float]:
    dist = distance(cur_lon, cur_lat, dst_lon, dst_lat)
    if dist <= 0.0 or meters <= 0.0:
        return cur_lon, cur_lat, 0.0

    step = min(meters, dist)
    ratio = step / dist
    new_lon = cur_lon + (dst_lon - cur_lon) * ratio
    new_lat = cur_lat + (dst_lat - cur_lat) * ratio
    new_lon = clamp(new_lon, -MAX_ONE_WAY_METERS, MAX_ONE_WAY_METERS)
    new_lat = clamp(new_lat, -MAX_ONE_WAY_METERS, MAX_ONE_WAY_METERS)
    return new_lon, new_lat, step


def latest_orders_map(data_dir: Path) -> dict[str, dict]:
    latest = {}
    for event in load_jsonl(data_dir / "orders.jsonl"):
        order_id = event.get("order_id")
        if order_id:
            latest[str(order_id)] = event
    return latest


def assigned_order_for_drone(drone_id: str, orders_map: dict[str, dict]) -> str | None:
    for order in orders_map.values():
        if order.get("status") == "assigned" and order.get("assigned_drone_id") == drone_id:
            return str(order.get("order_id"))
    return None


def can_start_outbound_mission(drone: dict, order: dict) -> bool:
    required = required_battery_with_reserve(order)
    if required > 100.0:
        return False
    return float(drone.get("battery_pct", 0.0)) >= required


def required_battery_with_reserve(order: dict) -> float:
    dest_lon = float(order.get("dest_lon", 0.0))
    dest_lat = float(order.get("dest_lat", 0.0))
    one_way = distance(WAREHOUSE[0], WAREHOUSE[1], dest_lon, dest_lat)
    roundtrip = one_way * 2.0
    return round((roundtrip * BATTERY_PER_METER) + BATTERY_RESERVE, 2)


def unassign_impossible_order(data_dir: Path, order: dict, ts: int) -> None:
    updated = dict(order)
    updated["timestamp"] = ts
    updated["updated_at"] = ts
    updated["status"] = "queued"
    updated["assigned_drone_id"] = None
    updated["note"] = "unassigned_impossible_roundtrip"
    append_jsonl(data_dir / "orders.jsonl", updated)


def mark_order_delivered(data_dir: Path, order_id: str, drone_id: str, ts: int) -> None:
    orders = latest_orders_map(data_dir)
    order = orders.get(order_id)
    if not order:
        return

    if order.get("status") == "delivered":
        return

    updated = dict(order)
    updated["timestamp"] = ts
    updated["updated_at"] = ts
    updated["status"] = "delivered"
    updated["delivered_by"] = drone_id
    updated["delivered_at"] = ts
    append_jsonl(data_dir / "orders.jsonl", updated)


def is_on_charging_point(drone: dict) -> bool:
    lon = float(drone.get("lon", 0.0))
    lat = float(drone.get("lat", 0.0))

    if distance(lon, lat, WAREHOUSE[0], WAREHOUSE[1]) <= CHECKPOINT_CHARGE_RADIUS:
        return True

    for cp in CHECKPOINTS:
        if distance(lon, lat, float(cp["lon"]), float(cp["lat"])) <= CHECKPOINT_CHARGE_RADIUS:
            return True
    return False


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
                "delivering_order_id": None,
                "charging": True,
                "flight_mode": None,  # outbound | return
                "phase_timer_s": 0.0,
                "target_lon": None,
                "target_lat": None,
                "outbound_distance": 0.0,
                "routing_progress": 0.0,
                "delivery_reported": False,
            }
        )
    return drones


def reset_mission(drone: dict) -> None:
    drone["assigned_order_id"] = None
    drone["delivering_order_id"] = None
    drone["flight_mode"] = None
    drone["phase_timer_s"] = 0.0
    drone["target_lon"] = None
    drone["target_lat"] = None
    drone["outbound_distance"] = 0.0
    drone["routing_progress"] = 0.0
    drone["delivery_reported"] = False


def update_drone(drone: dict, interval: float, orders_map: dict[str, dict], data_dir: Path, ts: int) -> dict:
    status = drone["status"]
    drone_id = drone["drone_id"]
    wind = random.uniform(0.0, 25.0)

    meters_moved = 0.0

    # Pickup assigned order when idle.
    if status == "landed" and not drone.get("assigned_order_id"):
        assigned = assigned_order_for_drone(drone_id, orders_map)
        if assigned:
            drone["assigned_order_id"] = assigned

    # Start outbound mission only from landed state.
    if status == "landed" and drone.get("assigned_order_id"):
        order = orders_map.get(drone["assigned_order_id"])
        if order and order.get("status") == "assigned":
            if required_battery_with_reserve(order) > 100.0:
                unassign_impossible_order(data_dir, order, ts)
                reset_mission(drone)
                return drone
            if can_start_outbound_mission(drone, order):
                drone["flight_mode"] = "outbound"
                drone["target_lon"] = float(order.get("dest_lon", 0.0))
                drone["target_lat"] = float(order.get("dest_lat", 0.0))
                drone["outbound_distance"] = distance(WAREHOUSE[0], WAREHOUSE[1], drone["target_lon"], drone["target_lat"])
                drone["routing_progress"] = 0.0
                drone["delivery_reported"] = False
                drone["phase_timer_s"] = TAKEOFF_SECONDS
                drone["status"] = "takingoff"
                status = drone["status"]

    if status == "takingoff":
        meters_moved = TAKEOFF_SPEED_MPS * interval
        drone["phase_timer_s"] = max(0.0, float(drone.get("phase_timer_s", 0.0)) - interval)
        if drone["phase_timer_s"] <= 0.0:
            if drone.get("flight_mode") == "outbound":
                drone["status"] = "routing"
            else:
                drone["status"] = "returning"

    elif status == "routing":
        step = ROUTING_SPEED_MPS * interval
        new_lon, new_lat, moved = move_towards(
            float(drone["lon"]),
            float(drone["lat"]),
            float(drone.get("target_lon", drone["lon"])),
            float(drone.get("target_lat", drone["lat"])),
            step,
        )
        drone["lon"], drone["lat"] = new_lon, new_lat
        meters_moved = moved
        drone["routing_progress"] = float(drone.get("routing_progress", 0.0)) + moved
        if drone["outbound_distance"] <= 0.0 or drone["routing_progress"] >= 0.35 * drone["outbound_distance"]:
            drone["status"] = "flying"

    elif status == "flying":
        step = FLYING_SPEED_MPS * interval
        new_lon, new_lat, moved = move_towards(
            float(drone["lon"]),
            float(drone["lat"]),
            float(drone.get("target_lon", drone["lon"])),
            float(drone.get("target_lat", drone["lat"])),
            step,
        )
        drone["lon"], drone["lat"] = new_lon, new_lat
        meters_moved = moved
        if distance(drone["lon"], drone["lat"], float(drone.get("target_lon", 0.0)), float(drone.get("target_lat", 0.0))) <= ARRIVAL_RADIUS:
            drone["status"] = "landing"
            drone["phase_timer_s"] = LANDING_SECONDS

    elif status == "landing":
        meters_moved = LANDING_SPEED_MPS * interval
        drone["phase_timer_s"] = max(0.0, float(drone.get("phase_timer_s", 0.0)) - interval)
        if drone["phase_timer_s"] <= 0.0:
            if drone.get("flight_mode") == "outbound":
                drone["status"] = "arrived"
                drone["phase_timer_s"] = ARRIVED_DWELL_SECONDS
            else:
                drone["status"] = "landed"
                drone["lon"] = WAREHOUSE[0]
                drone["lat"] = WAREHOUSE[1]
                reset_mission(drone)

    elif status == "arrived":
        if drone.get("assigned_order_id") and not drone.get("delivery_reported"):
            mark_order_delivered(data_dir, str(drone["assigned_order_id"]), drone_id, ts)
            drone["delivery_reported"] = True

        drone["phase_timer_s"] = max(0.0, float(drone.get("phase_timer_s", 0.0)) - interval)
        if drone["phase_timer_s"] <= 0.0:
            drone["flight_mode"] = "return"
            drone["target_lon"] = WAREHOUSE[0]
            drone["target_lat"] = WAREHOUSE[1]
            drone["status"] = "takingoff"
            drone["phase_timer_s"] = TAKEOFF_SECONDS

    elif status == "returning":
        step = RETURNING_SPEED_MPS * interval
        new_lon, new_lat, moved = move_towards(
            float(drone["lon"]),
            float(drone["lat"]),
            WAREHOUSE[0],
            WAREHOUSE[1],
            step,
        )
        drone["lon"], drone["lat"] = new_lon, new_lat
        meters_moved = moved
        if distance(drone["lon"], drone["lat"], WAREHOUSE[0], WAREHOUSE[1]) <= ARRIVAL_RADIUS:
            drone["status"] = "landing"
            drone["phase_timer_s"] = LANDING_SECONDS

    # Battery and wear dynamics.
    battery_drop = 0.0
    wear_drop = 0.0
    battery_gain = 0.0

    if drone["status"] in AIRBORNE_STATUSES or status in AIRBORNE_STATUSES:
        wind_factor = 1.0 + (wind / 100.0)
        battery_drop = meters_moved * BATTERY_PER_METER * wind_factor
        wear_drop = (meters_moved / 1000.0) * random.uniform(0.3, 1.2)
    elif drone["status"] in CHARGING_STATUSES and is_on_charging_point(drone):
        battery_gain = CHARGE_RATE_PCT_PER_SEC * interval

    drone["battery_pct"] = round(clamp(float(drone["battery_pct"]) - battery_drop + battery_gain, 0.0, 100.0), 2)
    drone["wear_pct"] = round(clamp(float(drone["wear_pct"]) - wear_drop, 0.0, 100.0), 2)
    drone["wind"] = round(wind, 2)

    drone["charging"] = drone["status"] in CHARGING_STATUSES and is_on_charging_point(drone)
    drone["delivering_order_id"] = drone.get("assigned_order_id") if drone["status"] in AIRBORNE_STATUSES else None

    return drone


def stream(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    ensure_data_files(data_dir)
    events_file = data_dir / "drone_events.jsonl"

    drones = init_drones()
    for _ in range(args.ticks):
        ts = int(time.time())
        orders_map = latest_orders_map(data_dir)

        for drone in drones:
            updated = update_drone(drone, args.interval, orders_map, data_dir, ts)
            event = {
                "timestamp": ts,
                "drone_id": updated["drone_id"],
                "status": updated["status"],
                "battery_pct": updated["battery_pct"],
                "wear_pct": updated["wear_pct"],
                "lon": round(updated["lon"], 2),
                "lat": round(updated["lat"], 2),
                "wind": updated["wind"],
                "charging": bool(updated.get("charging", False)),
                "assigned_order_id": updated.get("assigned_order_id"),
                "delivering_order_id": updated.get("delivering_order_id"),
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
