#!/usr/bin/env python3

import argparse
import json
import os
import random
import time
import uuid
from datetime import datetime

import requests
import paho.mqtt.client as mqtt
from kubernetes import client, config
from kubernetes.client.rest import ApiException

DEFAULT_NAMESPACE = "default"
DEFAULT_TOPIC_ORDERS = "business/ordini/nuovi"


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def monotonic_seconds():
    return time.monotonic()


def generate_random_coordinate(radius=5000.0, base_lat=0.0, base_lon=0.0):
    lat = base_lat + random.uniform(-radius, radius)
    lon = base_lon + random.uniform(-radius, radius)
    return round(lat, 2), round(lon, 2)


def generate_order():
    pickup_lat, pickup_lon = generate_random_coordinate()
    drop_lat, drop_lon = generate_random_coordinate()
    order_value = round(random.uniform(10.0, 150.0), 2)

    return {
        "order_id": f"ORD-{str(uuid.uuid4())[:8].upper()}",
        "status": "PENDING",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "drop_lat": drop_lat,
        "drop_lon": drop_lon,
        "weight_kg": round(random.uniform(0.5, 5.0), 2),
        "order_value_eur": order_value,
        "priority": "high" if order_value >= 100.0 else "normal" if order_value >= 50.0 else "low",
        "timestamp": time.time(),
    }


def mqtt_publish_orders(broker, port, topic, count, interval_sec):
    client_id = f"test-system-{random.randint(1000, 9999)}"
    client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    metrics = {"sent": 0, "failed": 0, "errors": []}

    try:
        client.connect(broker, port, 60)
    except Exception as exc:
        metrics["failed"] = count
        metrics["errors"].append(f"connect_error: {exc}")
        return metrics

    client.loop_start()
    try:
        for _ in range(count):
            payload = json.dumps(generate_order())
            try:
                msg_info = client.publish(topic, payload, qos=1)
                msg_info.wait_for_publish()
                if getattr(msg_info, "rc", None) != mqtt.MQTT_ERR_SUCCESS:
                    metrics["failed"] += 1
                    metrics["errors"].append(f"publish_rc: {getattr(msg_info, 'rc', 'unknown')}")
                else:
                    metrics["sent"] += 1
            except Exception as exc:
                metrics["failed"] += 1
                metrics["errors"].append(f"publish_error: {exc}")

            if interval_sec > 0:
                time.sleep(interval_sec)
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass

    return metrics


def http_check(url, timeout_sec=2):
    try:
        response = requests.get(url, timeout=timeout_sec)
        return response.status_code, None
    except Exception as exc:
        return None, str(exc)


def load_k8s_config():
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()


def get_deployment_replicas(apps_api, name, namespace):
    try:
        dep = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
        return dep.spec.replicas or 0
    except ApiException as e:
        raise


def set_deployment_replicas(apps_api, name, namespace, replicas):
    body = {"spec": {"replicas": replicas}}
    return apps_api.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)


def list_pods(core_api, namespace, label_selector):
    return core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)


def delete_one_pod(core_api, namespace, label_selector):
    pods = list_pods(core_api, namespace, label_selector)
    if not pods.items:
        return None
    pod_name = pods.items[0].metadata.name
    try:
        core_api.delete_namespaced_pod(name=pod_name, namespace=namespace)
    except ApiException:
        pass
    return pod_name


def wait_deployment_ready(apps_api, name, namespace, timeout_sec=60, poll=2):
    start = monotonic_seconds()
    while monotonic_seconds() - start < timeout_sec:
        try:
            deployment = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
            desired = deployment.spec.replicas or 0
            available = deployment.status.available_replicas or 0
            if available >= desired:
                return True
        except ApiException:
            pass
        time.sleep(poll)
    return False


def request_human_approval(mcp_url, token, action_type, payload, reason):
    headers = {"X-MCP-Token": token}
    body = {"name": "request_human_approval", "args": {"action_type": action_type, "payload": payload, "reason": reason}}
    resp = requests.post(f"{mcp_url.rstrip('/')}/tool", json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def check_pending_approvals(mcp_url, token):
    headers = {"X-MCP-Token": token}
    body = {"name": "check_pending_approvals", "args": {}}
    resp = requests.post(f"{mcp_url.rstrip('/')}/tool", json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def main():
    parser = argparse.ArgumentParser(description="System resilience test runner")
    parser.add_argument("--output", default="test_results.jsonl", help="Output file for JSONL results")
    parser.add_argument("--summary", default="test_results_summary.txt", help="Output file for summary")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--mqtt-broker", default=os.getenv("MQTT_BROKER", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--orders", type=int, default=100)
    parser.add_argument("--order-interval", type=float, default=0.2)
    parser.add_argument("--central-url", default=os.getenv("CENTRAL_URL", "http://localhost:5000"))
    parser.add_argument("--mcp-url", default=os.getenv("MCP_URL", "http://localhost:8101"))
    parser.add_argument("--mcp-token", default=os.getenv("MCP_TOKEN", "REDACTED_MCP_TOKEN"))
    parser.add_argument("--timeout", type=int, default=120, help="Readiness timeout (s) for deployments")
    parser.add_argument("--sleep-between", type=float, default=5.0, help="Seconds to sleep between tests")

    args = parser.parse_args()

    load_k8s_config()
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()

    results = []

    def record(event_type, data):
        entry = {"timestamp": now_iso(), "event": event_type, "data": data}
        results.append(entry)

    print(f"[RUN] Test runner started at {now_iso()}")

    # Test 1: Baseline availability
    print(f"[TEST 1/5] Baseline availability check -> {args.central_url}")
    status_code, err = http_check(args.central_url)
    record("baseline_central_health", {"status_code": status_code, "error": err})
    time.sleep(args.sleep_between)

    # Test 2: Stress test order load
    print(f"[TEST 2/5] Stress: publishing {args.orders} orders to {DEFAULT_TOPIC_ORDERS}")
    stress_start = monotonic_seconds()
    stress_metrics = mqtt_publish_orders(
        broker=args.mqtt_broker,
        port=args.mqtt_port,
        topic=DEFAULT_TOPIC_ORDERS,
        count=args.orders,
        interval_sec=args.order_interval,
    )
    stress_elapsed = monotonic_seconds() - stress_start
    record("stress_test", {
        "orders_sent": stress_metrics.get("sent", 0),
        "orders_failed": stress_metrics.get("failed", 0),
        "duration_sec": round(stress_elapsed, 2),
        "errors": stress_metrics.get("errors", [])[:10],
    })
    print(f"[TEST 2/5] Done: sent={stress_metrics.get('sent')} failed={stress_metrics.get('failed')} in {round(stress_elapsed,2)}s")
    time.sleep(args.sleep_between)

    # Test 3: Central server crash and recovery
    print("[TEST 3/5] Central server crash and recovery - deleting one central-server pod")
    central_test = {"deleted_pod": None, "delete_time": None, "downtime_sec": None, "recovery_time_sec": None, "error": None}
    try:
        pod = delete_one_pod(core_api, args.namespace, "app=central-server")
        if not pod:
            central_test["error"] = "no central-server pod found"
            print("[TEST 3/5] No central-server pod found")
        else:
            central_test["deleted_pod"] = pod
            central_test["delete_time"] = now_iso()
            print(f"[TEST 3/5] Deleted pod {pod} at {central_test['delete_time']}")

            # detect downtime and recovery via HTTP
            first_fail = None
            recovered = None
            start = monotonic_seconds()
            while monotonic_seconds() - start < args.timeout:
                sc, err = http_check(args.central_url)
                if sc is None:
                    if first_fail is None:
                        first_fail = monotonic_seconds()
                else:
                    if first_fail is not None:
                        recovered = monotonic_seconds()
                        break
                time.sleep(1)

            if first_fail and recovered:
                central_test["downtime_sec"] = round(recovered - first_fail, 2)
                central_test["recovery_time_sec"] = round(recovered - (time.monotonic() - (recovered - first_fail)), 2)
                print(f"[TEST 3/5] Recovered after {central_test['downtime_sec']}s")
            else:
                central_test["error"] = "recovery not observed within timeout"
                print("[TEST 3/5] Recovery not observed within timeout")

            # ensure deployment is ready
            ready = wait_deployment_ready(apps_api, "central-server", args.namespace, timeout_sec=args.timeout)
            if not ready and central_test.get("error") is None:
                central_test["error"] = "deployment not ready after timeout"
    except Exception as e:
        central_test["error"] = str(e)

    record("central_server_recovery", central_test)
    time.sleep(args.sleep_between)

    # Test 4: MQTT broker outage simulation
    print("[TEST 4/5] MQTT broker outage simulation: scale mosquitto to 0 then back to 1")
    broker_test = {"scaled_down": False, "scaled_up": False, "publish_during_outage": None, "recovery_publish": None, "outage_duration_sec": None, "error": None}
    original_replicas = None
    try:
        try:
            original_replicas = get_deployment_replicas(apps_api, "mosquitto", args.namespace)
        except ApiException:
            original_replicas = None

        t0 = monotonic_seconds()
        print(f"[TEST 4/5] Scaling mosquitto from {original_replicas} -> 0")
        set_deployment_replicas(apps_api, "mosquitto", args.namespace, 0)
        broker_test["scaled_down"] = True

        time.sleep(3)
        publish_outage = mqtt_publish_orders(broker=args.mqtt_broker, port=args.mqtt_port, topic=DEFAULT_TOPIC_ORDERS, count=3, interval_sec=0.1)
        broker_test["publish_during_outage"] = publish_outage
        print(f"[TEST 4/5] publish during outage: sent={publish_outage.get('sent')} failed={publish_outage.get('failed')}")

        print("[TEST 4/5] Scaling mosquitto back to 1 (or original replicas)")
        target_replicas = original_replicas if original_replicas and original_replicas > 0 else 1
        set_deployment_replicas(apps_api, "mosquitto", args.namespace, target_replicas)
        broker_test["scaled_up"] = True

        ready = wait_deployment_ready(apps_api, "mosquitto", args.namespace, timeout_sec=args.timeout)
        t1 = monotonic_seconds()

        publish_after = mqtt_publish_orders(broker=args.mqtt_broker, port=args.mqtt_port, topic=DEFAULT_TOPIC_ORDERS, count=3, interval_sec=0.1)
        broker_test["recovery_publish"] = publish_after

        if ready:
            broker_test["outage_duration_sec"] = round(t1 - t0, 2)
            print(f"[TEST 4/5] Mosquitto ready after {broker_test['outage_duration_sec']}s")
        else:
            broker_test["error"] = "mosquitto readiness timeout"
            print("[TEST 4/5] Mosquitto readiness timeout")
    except Exception as e:
        broker_test["error"] = str(e)

    record("mqtt_broker_outage", broker_test)
    time.sleep(args.sleep_between)

    # Test 5: Guardrail approval flow
    print("[TEST 5/5] Guardrail approval flow: request human approval for scaling > limit")
    guardrail_test = {"request": None, "pending": None, "error": None}
    try:
        req = request_human_approval(args.mcp_url, args.mcp_token, action_type="scale_drone_deployment", payload={"replicas": 10}, reason="Test guardrail: scaling beyond auto limit")
        pending = check_pending_approvals(args.mcp_url, args.mcp_token)
        guardrail_test["request"] = req
        guardrail_test["pending"] = pending
        print(f"[TEST 5/5] Guardrail request created: {req}")
    except Exception as e:
        guardrail_test["error"] = str(e)

    record("guardrail_human_approval", guardrail_test)

    # Persist results
    with open(args.output, "w") as f:
        for entry in results:
            f.write(json.dumps(entry) + "\n")

    summary_lines = [f"Test run at: {now_iso()}", f"Central URL: {args.central_url}", f"MQTT broker: {args.mqtt_broker}:{args.mqtt_port}", f"Orders: {args.orders} (interval {args.order_interval}s)", ""]
    for entry in results:
        summary_lines.append(f"- {entry['event']}: {json.dumps(entry['data'])}")

    with open(args.summary, "w") as f:
        f.write("\n".join(summary_lines) + "\n")

    print(f"[DONE] Results written to {args.output} and {args.summary}")


if __name__ == "__main__":
    main()
