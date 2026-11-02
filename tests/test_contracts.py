import hashlib
import pytest
from pydantic import ValidationError
from app.contracts import JobRequest, evaluate, digest_receipt


def test_sha256_known_vector():
    assert evaluate("sha256", "hello")["sha256"] == hashlib.sha256(b"hello").hexdigest()


def test_unicode_echo():
    assert evaluate("echo", "İstanbul") == {"value": "İstanbul"}


def test_word_count():
    assert evaluate("word_count", " one \n two  three ") == {"count": 3}


def test_receipt_is_deterministic():
    r = {"value": "x"}
    assert digest_receipt("abc", "echo", r) == digest_receipt("abc", "echo", r)


def test_receipt_changes_if_result_changes():
    assert digest_receipt("abc", "echo", {"value": "x"}) != digest_receipt("abc", "echo", {"value": "y"})


def test_forbidden_operation_rejected():
    with pytest.raises(ValidationError):
        JobRequest(operation="shell", input="whoami")


def test_input_length_bound():
    with pytest.raises(ValidationError):
        JobRequest(operation="echo", input="a" * 8193)


def test_fail_closed_runtime():
    with pytest.raises(ValueError):
        evaluate("exec", "rm -rf /")
