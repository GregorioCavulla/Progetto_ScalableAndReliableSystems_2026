from kubernetes import client, config
import os
try:
    config.load_incluster_config()
    conf = client.Configuration._default
    print("InCluster Config Loaded.")
    print("Host:", conf.host)
    print("Token Auth:", conf.api_key.get("authorization", "None")[:20] if conf.api_key else "No api_key dict")
except Exception as e:
    print("Failed to load:", e)
