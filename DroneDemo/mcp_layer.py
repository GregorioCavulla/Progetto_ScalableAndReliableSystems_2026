#!/usr/bin/env python3

import json
import math
import time
from pathlib import Path

WAREHOUSE = (0.0, 0.0)
MAX_COORD = 10000.0
MAX_ONE_WAY_METERS = math.sqrt(MAX_COORD ** 2 + MAX_COORD ** 2)
MAX_ROUNDTRIP_METERS = MAX_ONE_WAY_METERS * 2.0
BATTERY_PER_METER = 100.0 / MAX_ROUNDTRIP_METERS
WEAR_MIN_READY = 25.0
BATTERY_RESERVE = 15.0

URGENCY_PRIORITY = {
    "prioritario": 3,
    "normale": 2,
    "non_urgente": 1,
}


def now_ts() -> int:
    return int(time.time())


def distance(a_lon, a_lat, b_lon, b_lat) -> float:
    return math.sqrt((b_lon - a_lon) ** 2 + (b_lat - a_lat) ** 2)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def build_checkpoints(radius: float = 6000.0) -> list[dict]:
    out = []
    for idx in range(6):
        angle = math.radians(idx * 60)
        out.append(
            {
                "checkpoint_id": f"CP-{idx + 1}",
                "lon": round(radius * math.cos(angle), 2),
                "lat": round(radius * math.sin(angle), 2),
            }
        )
    return out


CHECKPOINTS = build_checkpoints()


class DroneMCP:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.drone_events_file = self.data_dir / "drone_events.jsonl"
        self.orders_file = self.data_dir / "orders.jsonl"
        self.actions_file = self.data_dir / "fleet_actions.jsonl"
        self.approvals_file = self.data_dir / "approvals.jsonl"

    def _latest_drone_states(self) -> dict[str, dict]:
        states = {}
        for event in load_jsonl(self.drone_events_file):
            drone_id = event.get("drone_id")
            if drone_id:
                states[drone_id] = event
        return states

    def _latest_orders(self) -> dict[str, dict]:
        states = {}
        for event in load_jsonl(self.orders_file):
            order_id = event.get("order_id")
            if order_id:
                states[order_id] = event
        return states

    def _latest_approvals(self) -> dict[str, dict]:
        states = {}
        for event in load_jsonl(self.approvals_file):
            req_id = event.get("request_id")
            if req_id:
                states[req_id] = event
        return states

    def get_fleet_snapshot(self) -> dict:
        drones = list(self._latest_drone_states().values())
        drones.sort(key=lambda d: d.get("drone_id", ""))

        summary = {
            "total": len(drones),
            "ready": 0,
            "low_battery": 0,
            "low_wear": 0,
            "avg_battery": 0.0,
            "avg_wear": 0.0,
        }

        if drones:
            battery_values = [float(d.get("battery_pct", 0.0)) for d in drones]
            wear_values = [float(d.get("wear_pct", 0.0)) for d in drones]
            summary["avg_battery"] = round(sum(battery_values) / len(drones), 2)
            summary["avg_wear"] = round(sum(wear_values) / len(drones), 2)

        for drone in drones:
            battery = float(drone.get("battery_pct", 0.0))
            wear = float(drone.get("wear_pct", 0.0))
            status = drone.get("status", "landed")
            ready = status in {"landed", "arrived"} and battery >= 35.0 and wear >= WEAR_MIN_READY
            if ready:
                summary["ready"] += 1
            if battery < 25.0:
                summary["low_battery"] += 1
            if wear < WEAR_MIN_READY:
                summary["low_wear"] += 1

        return {
            "warehouse": {"lon": WAREHOUSE[0], "lat": WAREHOUSE[1]},
            "battery_per_meter": round(BATTERY_PER_METER, 6),
            "drones": drones,
            "summary": summary,
        }

    def get_open_orders(self, limit: int = 50) -> dict:
        orders = [
            o
            for o in self._latest_orders().values()
            if o.get("status") in {"queued", "assigned"}
        ]
        orders.sort(
            key=lambda o: (
                -URGENCY_PRIORITY.get(o.get("urgency", "non_urgente"), 1),
                o.get("created_at", 0),
            )
        )
        return {
            "total_open": len(orders),
            "orders": orders[: max(1, int(limit))],
        }

    def estimate_order_cost(self, order_id: str) -> dict:
        order = self._latest_orders().get(order_id)
        if not order:
            return {"error": f"Order {order_id} not found"}

        dest_lon = float(order.get("dest_lon", 0.0))
        dest_lat = float(order.get("dest_lat", 0.0))
        one_way = distance(WAREHOUSE[0], WAREHOUSE[1], dest_lon, dest_lat)
        roundtrip = one_way * 2.0
        required_battery = round(roundtrip * BATTERY_PER_METER, 2)
        required_with_reserve = round(required_battery + BATTERY_RESERVE, 2)

        nearest_cp = min(
            CHECKPOINTS,
            key=lambda cp: distance(dest_lon, dest_lat, cp["lon"], cp["lat"]),
        )

        return {
            "order_id": order_id,
            "one_way_meters": round(one_way, 2),
            "roundtrip_meters": round(roundtrip, 2),
            "battery_required_pct": required_battery,
            "battery_required_with_reserve_pct": required_with_reserve,
            "nearest_checkpoint": nearest_cp,
        }

    def _drone_can_take_order(self, drone: dict, order_cost: dict) -> tuple[bool, str]:
        battery = float(drone.get("battery_pct", 0.0))
        wear = float(drone.get("wear_pct", 0.0))
        status = drone.get("status", "landed")

        if status not in {"landed", "arrived"}:
            return False, "drone_not_idle"
        if wear < WEAR_MIN_READY:
            return False, "wear_too_low"
        if battery < float(order_cost["battery_required_with_reserve_pct"]):
            return False, "battery_too_low"
        return True, "ok"

    def plan_dispatch(self) -> dict:
        drones = self._latest_drone_states()
        open_orders = self.get_open_orders(limit=200)["orders"]

        plan = []
        needs_approval = []

        for order in open_orders:
            order_cost = self.estimate_order_cost(order["order_id"])
            candidates = []

            for drone in drones.values():
                ok, reason = self._drone_can_take_order(drone, order_cost)
                if ok:
                    candidates.append(drone)

            candidates.sort(
                key=lambda d: (
                    -float(d.get("battery_pct", 0.0)),
                    -float(d.get("wear_pct", 0.0)),
                )
            )

            if candidates:
                best = candidates[0]
                plan.append(
                    {
                        "order_id": order["order_id"],
                        "urgency": order.get("urgency"),
                        "recommended_action": "assign_order",
                        "drone_id": best.get("drone_id"),
                    }
                )
                continue

            urgency = order.get("urgency", "non_urgente")
            if urgency == "prioritario":
                if float(order_cost.get("battery_required_with_reserve_pct", 101.0)) > 100.0:
                    needs_approval.append(
                        {
                            "kind": "checkpoint_drop",
                            "payload": {
                                "order_id": order["order_id"],
                                "checkpoint": order_cost.get("nearest_checkpoint"),
                            },
                            "reason": "Full delivery exceeds battery budget with reserve",
                        }
                    )
                else:
                    needs_approval.append(
                        {
                            "kind": "add_drone",
                            "payload": {"order_id": order["order_id"]},
                            "reason": "No current drone can safely deliver high-priority order",
                        }
                    )
            else:
                needs_approval.append(
                    {
                        "kind": "abort_order",
                        "payload": {"order_id": order["order_id"]},
                        "reason": "No safe assignment candidate for non-critical order",
                    }
                )

        return {
            "plan": plan,
            "approvals_needed": needs_approval,
            "open_orders": len(open_orders),
            "available_drones": len(drones),
        }

    def assign_order(self, drone_id: str, order_id: str) -> dict:
        drones = self._latest_drone_states()
        orders = self._latest_orders()

        drone = drones.get(drone_id)
        order = orders.get(order_id)
        if not drone:
            return {"error": f"Drone {drone_id} not found"}
        if not order:
            return {"error": f"Order {order_id} not found"}
        if order.get("status") != "queued":
            return {"error": f"Order {order_id} is not queued"}

        cost = self.estimate_order_cost(order_id)
        ok, reason = self._drone_can_take_order(drone, cost)
        if not ok:
            return {"error": f"Drone {drone_id} cannot take order: {reason}"}

        order_update = dict(order)
        order_update["status"] = "assigned"
        order_update["assigned_drone_id"] = drone_id
        order_update["updated_at"] = now_ts()
        append_jsonl(self.orders_file, order_update)

        action = {
            "timestamp": now_ts(),
            "action": "assign_order",
            "drone_id": drone_id,
            "order_id": order_id,
            "result": "executed",
        }
        append_jsonl(self.actions_file, action)
        return action

    def send_to_charge(self, drone_id: str) -> dict:
        drones = self._latest_drone_states()
        drone = drones.get(drone_id)
        if not drone:
            return {"error": f"Drone {drone_id} not found"}

        updated = dict(drone)
        updated["timestamp"] = now_ts()
        updated["status"] = "landed"
        updated["battery_pct"] = 100.0
        updated["lon"] = WAREHOUSE[0]
        updated["lat"] = WAREHOUSE[1]
        append_jsonl(self.drone_events_file, updated)

        action = {
            "timestamp": now_ts(),
            "action": "send_to_charge",
            "drone_id": drone_id,
            "result": "executed",
        }
        append_jsonl(self.actions_file, action)
        return action

    def send_to_repair(self, drone_id: str) -> dict:
        drones = self._latest_drone_states()
        drone = drones.get(drone_id)
        if not drone:
            return {"error": f"Drone {drone_id} not found"}

        updated = dict(drone)
        updated["timestamp"] = now_ts()
        updated["status"] = "landed"
        updated["wear_pct"] = 100.0
        updated["lon"] = WAREHOUSE[0]
        updated["lat"] = WAREHOUSE[1]
        append_jsonl(self.drone_events_file, updated)

        action = {
            "timestamp": now_ts(),
            "action": "send_to_repair",
            "drone_id": drone_id,
            "result": "executed",
        }
        append_jsonl(self.actions_file, action)
        return action

    def request_human_approval(self, kind: str, payload: dict, reason: str) -> dict:
        if kind not in {"add_drone", "abort_order", "checkpoint_drop"}:
            return {"error": f"Unknown approval kind: {kind}"}

        request_id = f"APR-{now_ts()}-{int(time.time() * 1000) % 10000}"
        req = {
            "timestamp": now_ts(),
            "request_id": request_id,
            "kind": kind,
            "payload": payload,
            "reason": reason,
            "status": "pending",
        }
        append_jsonl(self.approvals_file, req)
        return req

    def list_pending_approvals(self) -> dict:
        latest = self._latest_approvals()
        pending = [r for r in latest.values() if r.get("status") == "pending"]
        pending.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return {"count": len(pending), "items": pending}

    def apply_human_decision(self, request_id: str, approved: bool, note: str = "") -> dict:
        latest = self._latest_approvals().get(request_id)
        if not latest:
            return {"error": f"Approval request {request_id} not found"}
        if latest.get("status") != "pending":
            return {"error": f"Approval request {request_id} is already closed"}

        decision = {
            "timestamp": now_ts(),
            "request_id": request_id,
            "kind": latest.get("kind"),
            "payload": latest.get("payload"),
            "reason": latest.get("reason"),
            "status": "approved" if approved else "rejected",
            "note": note,
        }
        append_jsonl(self.approvals_file, decision)

        if approved:
            kind = latest.get("kind")
            payload = latest.get("payload", {})
            if kind == "add_drone":
                self._add_new_drone()
            elif kind == "abort_order":
                self._set_order_status(payload.get("order_id"), "aborted")
            elif kind == "checkpoint_drop":
                self._set_order_status(payload.get("order_id"), "checkpoint_drop")

        return decision

    def _set_order_status(self, order_id: str | None, status: str) -> None:
        if not order_id:
            return
        order = self._latest_orders().get(order_id)
        if not order:
            return
        updated = dict(order)
        updated["status"] = status
        updated["updated_at"] = now_ts()
        append_jsonl(self.orders_file, updated)

    def _add_new_drone(self) -> None:
        drones = self._latest_drone_states()
        max_num = 0
        for drone_id in drones.keys():
            if drone_id.startswith("D") and drone_id[1:].isdigit():
                max_num = max(max_num, int(drone_id[1:]))

        new_id = f"D{max_num + 1}"
        event = {
            "timestamp": now_ts(),
            "drone_id": new_id,
            "status": "landed",
            "battery_pct": 100.0,
            "wear_pct": 100.0,
            "lon": WAREHOUSE[0],
            "lat": WAREHOUSE[1],
            "wind": 0.0,
            "assigned_order_id": None,
        }
        append_jsonl(self.drone_events_file, event)


def ensure_data_files(data_dir: str | Path) -> None:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name in ["drone_events.jsonl", "orders.jsonl", "fleet_actions.jsonl", "approvals.jsonl"]:
        path = root / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
