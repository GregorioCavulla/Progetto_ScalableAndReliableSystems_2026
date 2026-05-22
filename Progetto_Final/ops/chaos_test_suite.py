import time
import logging
import os
import pathlib
import subprocess
import sys
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Risali alla root del progetto così che client_simulator.py sia raggiungibile
# anche quando lo script viene lanciato direttamente da ops/.
os.chdir(pathlib.Path(__file__).resolve().parent.parent)

# Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler("chaos_test_results.log"),
        logging.StreamHandler()
    ]
)

def setup_k8s():
    """Initializes Kubernetes client from local kubeconfig."""
    try:
        config.load_kube_config()
        logging.info("Kubernetes configuration loaded successfully.")
        return client.AppsV1Api(), client.CoreV1Api()
    except Exception as e:
        logging.error(f"Failed to load kube_config: {e}")
        return None, None

def test_graceful_degradation_influxdb(apps_api):
    logging.info("=== TEST 1: Primary Database Outage (Graceful Degradation) ===")
    namespace = "default"
    deployment_name = "influxdb"
    rto = None

    try:
        logging.info(f"Scaling {deployment_name} down to 0 replicas...")
        body = {'spec': {'replicas': 0}}
        apps_api.patch_namespaced_deployment_scale(name=deployment_name, namespace=namespace, body=body)

        logging.info("Waiting for pods to terminate (10 seconds)...")
        time.sleep(10)

        start_recovery_time = time.time()
        logging.info(f"Restoring {deployment_name} to 1 replica...")
        body = {'spec': {'replicas': 1}}
        apps_api.patch_namespaced_deployment_scale(name=deployment_name, namespace=namespace, body=body)

        while True:
            deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            if deployment.status.ready_replicas == 1:
                end_recovery_time = time.time()
                rto = end_recovery_time - start_recovery_time
                logging.info(f"InfluxDB is back online! RTO (Recovery Time Objective): {rto:.2f} seconds.")
                break
            time.sleep(2)

    except ApiException as e:
        logging.error(f"K8s API Error during InfluxDB test: {e.reason}")
    logging.info("=== END TEST 1 ===\n")
    return rto


def test_network_resilience_mqtt(core_api):
    logging.info("=== TEST 2: Network Resilience (MQTT Broker Crash) ===")
    namespace = "default"
    label_selector = "app=mosquitto"
    downtime = None

    try:
        pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        if not pods.items:
            logging.warning("No Mosquitto pods found. Skipping test.")
            return None

        pod_name = pods.items[0].metadata.name
        logging.info(f"Deleting Mosquitto pod: {pod_name} to simulate a crash...")

        start_time = time.time()
        core_api.delete_namespaced_pod(name=pod_name, namespace=namespace)

        logging.info("Waiting for Kubernetes deployment to spin up a new Mosquitto pod...")
        while True:
            pods = core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
            ready_pods = [p for p in pods.items if p.status.phase == "Running"]
            if ready_pods:
                end_time = time.time()
                downtime = end_time - start_time
                logging.info(f"New Mosquitto pod is Running. Downtime: {downtime:.2f} seconds.")
                logging.info("Drones should now be autonomously reconnecting via Exponential Backoff (paho-mqtt).")
                break
            time.sleep(2)

    except ApiException as e:
        logging.error(f"K8s API Error during MQTT test: {e.reason}")
    logging.info("=== END TEST 2 ===\n")
    return downtime


def test_load_spike(apps_api):
    logging.info("=== TEST 3: Load Spike and Dynamic Scaling ===")
    logging.info("Injecting massive load using client_simulator.py --stress...")
    drones_before = 0
    drones_after = 0
    namespace = "default"
    deployment_name = "drone-simulator"

    try:
        # Get replicas before spike
        deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        drones_before = deployment.spec.replicas

        logging.info("Executing client_simulator.py --stress to generate 50 requests...")
        process = subprocess.Popen(
            ["python3", "client_simulator.py", "--stress"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        logging.info("Allowing 60 seconds for Logistic AI Brain to detect queue spike and scale drone deployment...")
        time.sleep(60)

        if process.poll() is None:
            process.terminate()

        # Get replicas after spike
        deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        drones_after = deployment.spec.replicas

        logging.info(f"Replicas comparison: Before={drones_before} | After={drones_after}")

    except FileNotFoundError:
        logging.error("Failed to run client_simulator.py, check if it's executable.")
    except ApiException as e:
        logging.error(f"K8s API Error reading drone deployment: {e.reason}")

    logging.info("=== END TEST 3 ===\n")
    return {"before": drones_before, "after": drones_after}


def interactive_menu():
    apps_v1, core_v1 = setup_k8s()
    if not apps_v1 or not core_v1:
        logging.error("Could not setup K8s client. Exiting.")
        sys.exit(1)

    while True:
        print("\n" + "="*50)
        print("   Chaos Engineering Test Suite Menu")
        print("="*50)
        print("1. Test Primary Database Outage (InfluxDB Graceful Degradation)")
        print("2. Test Network Resilience (MQTT Broker Crash & Backoff)")
        print("3. Test Load Spike & Dynamic AI Scaling")
        print("4. Run ALL Tests")
        print("q. Quit")
        print("="*50)

        choice = input("Select an option [1-4, q]: ").strip().lower()

        if choice == '1':
            rto = test_graceful_degradation_influxdb(apps_v1)
            print("\n*** RISULTATI TEST 1 ***")
            print(f"-> InfluxDB RTO (Recovery Time Objective): {rto:.2f} secondi" if rto else "-> Errore nel test o pod non trovato.")

        elif choice == '2':
            downtime = test_network_resilience_mqtt(core_v1)
            print("\n*** RISULTATI TEST 2 ***")
            print(f"-> Tempo K8s Recovery Mosquitto: {downtime:.2f} secondi" if downtime else "-> Errore nel test o pod non trovato.")

        elif choice == '3':
            result = test_load_spike(apps_v1)
            print("\n*** RISULTATI TEST 3 ***")
            print(f"-> Drone Replicas PRIMA dello Spike: {result['before']}")
            print(f"-> Drone Replicas DOPO lo Spike: {result['after']}")

        elif choice == '4':
            rto = test_graceful_degradation_influxdb(apps_v1)
            downtime = test_network_resilience_mqtt(core_v1)
            result = test_load_spike(apps_v1)

            print("\n" + "*"*50)
            print("   RESOCONTO COMPLETO E2E TEST")
            print("*"*50)
            print(f"[TEST 1] InfluxDB RTO: {rto:.2f} s" if rto else "[TEST 1] InfluxDB RTO: N/A")
            print(f"[TEST 2] Mosquitto K8s Downtime: {downtime:.2f} s" if downtime else "[TEST 2] Mosquitto K8s Downtime: N/A")
            print(f"[TEST 3] AI Scaling -> Da {result['before']} a {result['after']} droni")

        elif choice == 'q':
            print("Uscita dalla Test Suite.")
            break
        else:
            print("Scelta non valida, riprova.")

if __name__ == '__main__':
    interactive_menu()
