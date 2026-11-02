# Agent Runtime Proof

A small, inspectable reference service demonstrating **agent-job orchestration, idempotent submission, safe bounded execution, and verifiable receipts**.

**Stack:** Python 3.11+, FastAPI, Redis Streams, Qdrant, Docker Compose; optional k3s manifests.

## What it actually does
- Accepts jobs over REST with an idempotency key.
- Uses Redis Streams to hand work to a separately running worker.
- Only executes three non-network, no-shell operations: `echo`, `sha256`, and `word_count`.
- Stores per-job state and a SHA-256 evidence digest in Redis. Failed jobs remain inspectable.
- Stores/searches caller-supplied numeric vectors in Qdrant (no claims of learned embeddings).
- Exposes liveness and readiness separately.
- Provides unit tests of deterministic, side-effect-free task logic.

**Not an autonomous LLM service.** It deliberately leaves model/provider adapters outside the proof. This avoids claiming capabilities that are not implemented.

## Quick start
```bash
docker compose up --build -d
curl -s http://127.0.0.1:8000/health/ready
curl -s -X POST http://127.0.0.1:8000/v1/jobs \
  -H 'content-type: application/json' -H 'Idempotency-Key: demo-001' \
  -d '{"operation":"sha256","input":"hello agent"}'
# Get /v1/jobs/{job_id} using the returned ID
docker compose logs -f worker
docker compose down
```

## Evidence API
`POST /v1/evidence` accepts `{"id":"doc-1","vector":[0.1,0.2,0.3,0.4],"text":"Example","source":"demo"}`.
`POST /v1/evidence/query` accepts `{"vector":[0.1,0.2,0.3,0.4],"limit":3}`. The vector must come from your own encoder, and its dimension is fixed at 4 for this proof. Production would use a real embedding provider and versioned encoder metadata.

## Local Python tests
```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```
Integration smoke (Redis/Qdrant/Docker required): `bash scripts/smoke.sh`.

## k3s
`kubectl apply -k deploy/k3s` deploys cluster-internal, **ephemeral** Redis/Qdrant plus API and worker. No ingress or storage persistence is configured. This is a lab manifest, **not** a production-ready HA chart. Replace with secured, persistent dependencies and secrets management for production.

## Security and limitations
- API has **no authentication**; the Compose example binds HTTP to localhost only. Do not expose it publicly.
- Qdrant is reachable only on a local loopback binding in Compose; no Qdrant credentials in this lab.
- Redis does not implement lease recovery, consumer pending-claim retry, or exactly-once execution. Redis Streams give at-least-once delivery with this implementation; deterministic operations allow safe reprocessing, but **end-to-end exactly-once is not claimed**.
- Idempotency key is bounded by the API schema and has a 24-hour TTL; a lost publish after claiming the key can leave a pending record. Production requires an atomic Lua transaction or transactional outbox.
- No SSRF, subprocess execution, shell access, outbound model calls, or arbitrary code execution.
- No performance or availability SLA claimed. Confirm outcomes from live test/CI receipts, not this README.

## Provenance
Public demonstration authored for job applications, November 2026. Inspired by earlier multi-provider routing, verification and replay concepts in private `claude-duzen`/Orkestral work, but does not expose private source, secrets, or user data. This README does not claim that any external deployment exists.
