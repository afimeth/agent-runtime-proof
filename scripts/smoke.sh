#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://127.0.0.1:8000}
curl --fail --silent "$BASE/health/ready"
echo
PAYLOAD='{"operation":"word_count","input":"Agent systems need proof"}'
RESP=$(curl --fail --silent -X POST "$BASE/v1/jobs" -H 'Content-Type: application/json' -H 'Idempotency-Key: smoke-00001' -d "$PAYLOAD")
echo "$RESP"
ID=$(printf '%s' "$RESP" | python -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')
for _ in $(seq 1 15); do
  J=$(curl --fail --silent "$BASE/v1/jobs/$ID")
  if printf '%s' "$J" | grep -q '"status":"done"'; then
    echo "$J"
    exit 0
  fi
  sleep 1
done
echo "Worker did not finish within smoke window" >&2
exit 1
