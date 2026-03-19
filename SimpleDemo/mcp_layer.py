#!/usr/bin/env python3

import json
from collections import Counter


class SimpleMCP:
    """Tiny local MCP-like layer with only 3 public methods."""

    def __init__(self, events):
        self.events = events

    def get_recent_events(self, limit=5, state=None):
        data = self.events[-limit:]
        if state is not None:
            data = [e for e in data if e.get("state") == state]
        return data

    def get_system_status(self, window=20):
        sample = self.events[-window:] if self.events else []
        counts = Counter(e.get("state", "unknown") for e in sample)
        total = len(sample)
        error_ratio = (counts.get("error", 0) / total) if total else 0.0

        if error_ratio >= 0.25:
            health = "critical"
        elif counts.get("warning", 0) > 0:
            health = "degraded"
        else:
            health = "healthy"

        return {
            "health": health,
            "sample_size": total,
            "counts": dict(counts),
            "error_ratio": round(error_ratio, 3),
        }

    def run_remediation(self):
        status = self.get_system_status(window=20)
        if status["health"] == "critical":
            return {
                "action": "restart_worker_simulated",
                "result": "executed",
            }
        if status["health"] == "degraded":
            return {
                "action": "clear_cache_simulated",
                "result": "executed",
            }
        return {
            "action": "no_action",
            "result": "skipped",
        }


def load_events_from_jsonl(path):
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events
