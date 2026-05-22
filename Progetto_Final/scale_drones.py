import os
import sys
import time
from kubernetes import client, config

def main():
    try:
        # Tenta di caricare la configurazione in-cluster se sta girando dentro un pod
        config.load_incluster_config()
        # Workaround per il bug noto del client Python K8s
        # (api_key usa 'authorization' invece di 'BearerToken' in alcune versioni)
        api_config = client.Configuration.get_default_copy()
        api_config.api_key['BearerToken'] = api_config.api_key.get('authorization')
        api_client = client.ApiClient(api_config)
        v1 = client.AppsV1Api(api_client)
        print("[Scale CLI] Configurazione in-cluster caricata.")
    except config.ConfigException:
        # Fallback alla configurazione locale (~/.kube/config) se eseguito dall'esterno
        try:
            config.load_kube_config()
            v1 = client.AppsV1Api()
            print("[Scale CLI] Configurazione kubeconfig locale caricata.")
        except Exception as e:
            print(f"[Scale CLI] Errore critico. Impossibile contattare Kubernetes: {e}")
            sys.exit(1)

    print("\n=== K8s Drone Scaler ===")
    print("Digita il numero di droni (repliche) desiderati (es. 5)")
    print("Digita 'exit' o 'q' per uscire")
    print("========================\n")

    while True:
        try:
            cmd = input("replicas> ").strip()
            
            if cmd in ["exit", "q", "quit"]:
                print("[Scale CLI] Uscita.")
                break
            
            if not cmd:
                continue

            try:
                replicas = int(cmd)
                if replicas < 0:
                    print("[Scale CLI] Il numero di repliche non può essere negativo.")
                    continue
                    
                print(f"[Scale CLI] Patching deployment 'drone-simulator' a {replicas} repliche...")
                
                v1.patch_namespaced_deployment_scale(
                    name="drone-simulator",
                    namespace="default",
                    body={"spec": {"replicas": replicas}}
                )
                print(f"[Scale CLI] OK! Kubernetes sta scalando la flotta a {replicas} unita'.\n")
                
            except ValueError:
                print("[Scale CLI] Errore: inserisci un formato numerico valido.")
            except client.rest.ApiException as api_err:
                print(f"[Scale CLI] API Error K8s: HTTP {api_err.status} - {api_err.reason}")
                
        except KeyboardInterrupt:
            print("\n[Scale CLI] Uscita forzata.")
            break

if __name__ == "__main__":
    main()