"""Deterministic operations. No eval, shell, network, or mutable side effects."""
from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, Field

Operation = Literal["echo", "sha256", "word_count"]


class JobRequest(BaseModel):
    operation: Operation
    input: str = Field(max_length=8192)


def evaluate(operation: Operation, text: str) -> dict:
    if operation == "echo":
        return {"value": text}
    if operation == "sha256":
        return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if operation == "word_count":
        return {"count": len(text.split())}
    raise ValueError("unsupported operation")


def digest_receipt(job_id: str, operation: str, result: dict) -> str:
    canonical = json.dumps(
        {"job_id": job_id, "operation": operation, "result": result},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
