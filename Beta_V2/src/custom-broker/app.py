import logging
import json
from typing import Dict, List

from fastapi import FastAPI, Request, Response

app = FastAPI()
queues: Dict[str, List[bytes]] = {}
total_published = 0
total_consumed = 0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.post("/publish/{queue_name}")
async def publish(queue_name: str, request: Request):
    global total_published
    payload = await request.body()
    queues.setdefault(queue_name, []).append(payload)
    total_published += 1
    return {"status": "ok", "queue": queue_name, "size": len(queues[queue_name])}


@app.get("/consume/{queue_name}")
async def consume(queue_name: str):
    global total_consumed
    items = queues.get(queue_name, [])
    if not items:
        return Response(status_code=404, content="Queue empty")
    payload = items.pop(0)
    total_consumed += 1
    return Response(content=payload)


@app.get("/api/queues")
def get_queues_snapshot():
    sizes = {name: len(items) for name, items in queues.items()}
    return {
        "queues": sizes,
        "total_published": total_published,
        "total_consumed": total_consumed,
    }


@app.get("/api/queues/{queue_name}")
def get_queue_size(queue_name: str):
    return {"queue": queue_name, "size": len(queues.get(queue_name, []))}


@app.get("/api/queues/{queue_name}/peek")
def peek_queue(queue_name: str, limit: int = 10):
    safe_limit = max(1, min(limit, 100))
    items = queues.get(queue_name, [])[:safe_limit]
    decoded = []
    for payload in items:
        try:
            decoded.append(json.loads(payload.decode("utf-8")))
        except Exception:
            decoded.append(payload.decode("utf-8", errors="replace"))
    return {"queue": queue_name, "size": len(queues.get(queue_name, [])), "items": decoded}


@app.get("/health")
def health():
    return "ok"
