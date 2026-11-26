"""Spec Extraction AI step: every way of getting no result says why, the key is found in the server settings too, and the key
never appears in the request URL, the error text or the log. The AI service is mocked - nothing is sent anywhere."""
import json
import logging
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import sdie_extractor as X  # noqa: E402

KEY = "test-key-123456"


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def answer(text, finish="STOP", extra=()):
    return Resp(200, {"candidates": [{"finishReason": finish, "content": {"parts": [*extra, {"text": text}]}}]})


GOOD = json.dumps({"sections": [{"heading": "PT", "instrument_type": "PRESSURE TRANSMITTER",
                                 "specs": {"RANGE": {"values": ["0-10 bar"], "confidence": 95}}}]})


@pytest.fixture()
def call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = {}

    def use(response):
        def post(url, **kw):
            seen.update(url=url, **kw)
            if isinstance(response, Exception):
                raise response
            return response
        monkeypatch.setattr(requests, "post", post)
        return seen
    return use


def test_success_ignores_thought_parts_and_sends_the_key_only_in_a_header(call):
    seen = call(answer(GOOD, extra=[{"text": "thinking about it", "thought": True}]))
    sections, kind = X._run_ai_extraction("Range : 0-10 bar")
    assert kind == "PRESSURE TRANSMITTER" and sections[0]["specs"][0]["value"] == "0-10 bar"
    assert KEY not in seen["url"] and seen["headers"]["x-goog-api-key"] == KEY
    cfg = seen["json"]["generationConfig"]
    assert cfg["maxOutputTokens"] >= 16000 and "temperature" not in cfg and cfg["responseMimeType"] == "application/json"


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    with pytest.raises(X.ExtractionError, match="not configured"):
        X._run_ai_extraction("text")


def test_key_from_the_server_settings_is_used_when_it_is_not_in_the_environment(call, monkeypatch):
    seen = call(answer(GOOD))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "from-settings")
    assert X._run_ai_extraction("text")[0]
    assert seen["headers"]["x-goog-api-key"] == "from-settings"


@pytest.mark.parametrize("response, expected", [
    (Resp(403, {"error": {"message": f"API key {KEY} is invalid"}}), "refused the API key"),
    (Resp(404, {"error": {"message": "model not found"}}), "not available"),
    (Resp(429, {"error": {"message": "quota"}}), "quota"),
    (Resp(503), "temporarily unavailable"),
    (requests.Timeout(), "did not answer"),
    (requests.ConnectionError(f"https://x?key={KEY}"), "could not reach"),
    (answer(GOOD[:20], finish="MAX_TOKENS"), "cut off"),
    (Resp(200, {"candidates": [{"finishReason": "SAFETY"}]}), "no text.*SAFETY"),
    (Resp(200, {}), "could not be read"),
    (answer("not json at all"), "expected format"),
    (answer(json.dumps({"sections": [{"heading": "x", "specs": {}}]})), "no instrument specifications"),
])
def test_every_failure_says_why_without_leaking_the_key(call, caplog, response, expected):
    call(response)
    with caplog.at_level(logging.DEBUG), pytest.raises(X.ExtractionError, match=expected) as err:
        X._run_ai_extraction("Range : 0-10 bar")
    assert KEY not in str(err.value) and KEY not in caplog.text


def test_unreadable_scan_is_reported(call):
    call(answer(GOOD))
    with pytest.raises(X.ExtractionError, match="No readable text"):
        X._run_ai_extraction("   ")


def test_the_job_shows_the_reason_to_the_user(call, monkeypatch):
    from app.routers import sdie
    call(Resp(429, {"error": {"message": "quota"}}))
    monkeypatch.setattr(X, "extract_pages", lambda b, n: ["page"])
    monkeypatch.setattr(X, "ocr_page", lambda p: [{"text": "Range : 0-10 bar", "confidence": 90}])
    sdie._run_extraction_job("job-1", b"x", "a.png", 1)
    assert sdie.extraction_jobs["job-1"]["status"] == "error" and "quota" in sdie.extraction_jobs["job-1"]["error"]
