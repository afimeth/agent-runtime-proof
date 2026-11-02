"""FastAPI HTTP gateway; lab-only API with no authentication."""
from __future__ import annotations

import json
import os
import uuid
from typing import Annotated
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from redis import Redis, RedisError
from qdrant_client import QdrantClient, models

from app.contracts import JobRequest

app = FastAPI(title="Agent Runtime Proof", version="0.1.0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
STREAM = "jobs:stream"
COLLECTION = "demo_evidence_v1"
VECTOR_SIZE = 4


def redis_client() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)


def qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, timeout=3)


@app.get("/health/live")
def live():
    return {"status": "live"}


@app.get("/health/ready")
def ready():
    try:
        redis_client().ping()
        qdrant_client().get_collections()
    except Exception:
        raise HTTPException(status_code=503, detail="dependency unavailable")
    return {"status": "ready"}


@app.post("/v1/jobs", status_code=202)
def submit(job: JobRequest, idempotency_key: Annotated[str, Header(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9._-]+$")]):
    r = redis_client()
    idem = "idem:" + idempotency_key
    job_id = str(uuid.uuid4())
    # Not atomic with XADD; document the failure window in README.
    if not r.set(idem, job_id, nx=True, ex=86400):
        existing = r.get(idem)
        if not existing:
            raise HTTPException(status_code=409, detail="idempotency race")
        old = r.hgetall("job:" + existing)
        if old and old.get("operation") != job.operation:
            raise HTTPException(status_code=409, detail="idempotency key reused for different operation")
        return {"job_id": existing, "status": old.get("status", "pending")}

    try:
        r.hset("job:" + job_id, mapping={"status": "queued", "operation": job.operation, "input": job.input})
        r.expire("job:" + job_id, 86400)
        r.xadd(STREAM, {"job_id": job_id}, maxlen=10000, approximate=True)
    except RedisError:
        raise HTTPException(status_code=503, detail="queue unavailable")
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid job id")
    job = redis_client().hgetall("job:" + job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {k: json.loads(v) if k == "result" else v for k, v in job.items() if k != "input"}


class Evidence(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    vector: list[float] = Field(min_length=VECTOR_SIZE, max_length=VECTOR_SIZE)
    text: str = Field(max_length=4096)
    source: str = Field(max_length=255)


class EvidenceQuery(BaseModel):
    vector: list[float] = Field(min_length=VECTOR_SIZE, max_length=VECTOR_SIZE)
    limit: int = Field(default=3, ge=1, le=20)


def ensure_collection(client: QdrantClient):
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )


@app.post("/v1/evidence")
def add_evidence(doc: Evidence):
    try:
        client = qdrant_client()
        ensure_collection(client)
        # Stable point UUID from caller-supplied identifier; plaintext kept in payload.
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "agent-runtime-proof/" + doc.id))
        client.upsert(collection_name=COLLECTION, points=[
            models.PointStruct(id=point_id, vector=doc.vector, payload={
                "external_id": doc.id, "text": doc.text, "source": doc.source,
            })
        ], wait=True)
        return {"id": doc.id, "stored": True}
    except Exception:
        raise HTTPException(status_code=503, detail="vector service unavailable")


@app.post("/v1/evidence/query")
def search_evidence(q: EvidenceQuery):
    try:
        client = qdrant_client()
        ensure_collection(client)
        result = client.query_points(collection_name=COLLECTION, query=q.vector, limit=q.limit, with_payload=True)
        return {"hits": [{"score": p.score, "payload": p.payload} for p in result.points]}
    except Exception:
        raise HTTPException(status_code=503, detail="vector service unavailable")
