"""Redis Streams consumer. Operations are deterministic and have no external effects."""
from __future__ import annotations

import json
import os
import socket
import time
from redis import Redis, ResponseError
from app.contracts import evaluate, digest_receipt

URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STREAM = "jobs:stream"
GROUP = "proof-workers"
CONSUMER = socket.gethostname()


def run_forever():
    r = Redis.from_url(URL, decode_responses=True, socket_timeout=5)
    for _ in range(30):
        try:
            r.ping()
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Redis unavailable")

    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    while True:
        events = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=8, block=2000)
        for _, messages in events:
            for msg_id, fields in messages:
                job_id = fields["job_id"]
                key = "job:" + job_id
                record = r.hgetall(key)
                if not record:
                    r.xack(STREAM, GROUP, msg_id)
                    continue
                if record.get("status") == "done":
                    r.xack(STREAM, GROUP, msg_id)
                    continue
                try:
                    operation = record["operation"]
                    result = evaluate(operation, record["input"])
                    receipt = digest_receipt(job_id, operation, result)
                    r.hset(key, mapping={
                        "status": "done", "result": json.dumps(result, ensure_ascii=False),
                        "receipt_sha256": receipt,
                    })
                except Exception as exc:
                    r.hset(key, mapping={"status": "failed", "error": type(exc).__name__})
                r.xack(STREAM, GROUP, msg_id)


if __name__ == "__main__":
    run_forever()
