import asyncio
import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI

from buzz import meeting_translator as module
from buzz.meeting_config import MeetingConfigError
from buzz.meeting_translator import MeetingTranslator, PendingTranslation

TEST_MODEL = "test-model"
TEST_BASE_URL = "https://translation.example.invalid/v1"


def response(parts=("下周", "部署。"), finish="stop"):
    events = []
    for part in parts:
        events.append({"choices": [{"index": 0, "delta": {"content": part},
                                    "finish_reason": None}]})
    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    body = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                          content=body + "data: [DONE]\n\n")


def install_transport(monkeypatch, handler):
    def client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False))
    monkeypatch.setattr(module, "AsyncOpenAI", client)


@pytest.fixture
def worker():
    return MeetingTranslator(SimpleNamespace(llm_model=TEST_MODEL, llm_prompt="翻译成中文"),
                             api_key="test-credential", base_url=TEST_BASE_URL, request_timeout=1)


@pytest.fixture
def run_worker(qtbot):
    running = []

    def run(worker):
        thread = threading.Thread(target=worker.start, daemon=True)
        running.append((worker, thread))
        thread.start()
        return thread

    yield run
    for worker, thread in running:
        worker.stop()
        thread.join(timeout=2)
        assert not thread.is_alive(), "Translation did not stop promptly"


def test_stream_updates_same_segment_and_preserves_request_contract(monkeypatch, qtbot, worker, run_worker):
    requests, partials, finals = [], [], []

    def handler(request):
        requests.append(request)
        return response()

    install_transport(monkeypatch, handler)
    worker.partial_translation.connect(lambda text, sid: partials.append((text, sid)))
    worker.translation.connect(lambda text, sid: finals.append((text, sid)))
    worker.enqueue("Deploy next week.", 7)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(finals))
    assert partials[0] == ("下周", 7)
    assert finals == [("下周部署。", 7)]
    assert str(requests[0].url) == TEST_BASE_URL + "/chat/completions"
    body = json.loads(requests[0].content)
    assert body["model"] == TEST_MODEL
    assert body["max_completion_tokens"] == 512
    assert body["stream"] is True
    assert body["messages"][-1] == {"role": "user", "content": "Deploy next week."}


def test_order_and_bounded_context(monkeypatch, qtbot, worker, run_worker):
    payloads, finals = [], []

    def handler(request):
        payloads.append(json.loads(request.content))
        return response()

    install_transport(monkeypatch, handler)
    worker.translation.connect(lambda text, sid: finals.append(sid))
    for i in range(6):
        assert worker.enqueue(f"Sentence {i}.", i)
    run_worker(worker)
    qtbot.waitUntil(lambda: len(finals) == 6)
    assert finals == list(range(6))
    assert payloads[1]["messages"][1:3] == [
        {"role": "user", "content": "Sentence 0."},
        {"role": "assistant", "content": "下周部署。"}]
    assert len(payloads[-1]["messages"]) == 8  # system + 3 turns + current
    assert payloads[-1]["messages"][1]["content"] == "Sentence 2."


def test_full_queue_rejects_explicitly_without_blocking(qtbot, worker):
    errors = []
    worker.error.connect(lambda message, sid: errors.append(sid))
    for i in range(6):
        assert worker.enqueue("Pending", i)
    assert not worker.enqueue("Overflow", 6)
    assert errors == [6]
    assert worker.queue.qsize() == 6
    worker.stop()
    assert worker.queue.empty()
    assert not worker.enqueue("After stop", 7)


def test_stale_caption_skipped_but_new_caption_translated(monkeypatch, qtbot, worker, run_worker):
    payloads, errors, finals = [], [], []

    def handler(request):
        payloads.append(json.loads(request.content))
        return response()

    install_transport(monkeypatch, handler)
    worker.error.connect(lambda message, sid: errors.append(sid))
    worker.translation.connect(lambda text, sid: finals.append(sid))
    worker.queue.put(PendingTranslation("Old", 1, time.monotonic() - 30))
    worker.enqueue("Current", 2)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(finals))
    assert errors == [1]
    assert finals == [2]
    assert len(payloads) == 1
    assert payloads[0]["messages"][-1]["content"] == "Current"


def test_stop_before_start_sends_no_requests(monkeypatch, qtbot, worker, run_worker):
    calls = []
    install_transport(monkeypatch, lambda request: calls.append(request) or response())
    worker.enqueue("Pending", 1)
    worker.stop()
    thread = run_worker(worker)
    thread.join(1)
    assert not thread.is_alive()
    assert not calls


def test_stop_cancels_inflight_request_and_discards_pending(monkeypatch, qtbot, worker, run_worker):
    entered, cancelled = threading.Event(), threading.Event()
    calls, finals = [], []

    async def handler(request):
        calls.append(request)
        entered.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    install_transport(monkeypatch, handler)
    worker.translation.connect(lambda text, sid: finals.append(sid))
    worker.enqueue("In flight", 1)
    worker.enqueue("Pending", 2)
    thread = run_worker(worker)
    qtbot.waitUntil(entered.is_set)
    worker.stop()
    worker.stop()  # Repeated UI shutdown must not interrupt transport cleanup.
    thread.join(1)
    assert not thread.is_alive()
    assert cancelled.is_set()
    assert len(calls) == 1
    assert not finals
    assert worker.queue.empty()


def test_deadline_reports_error_and_worker_continues(monkeypatch, qtbot, worker, run_worker):
    errors, finals = [], []
    count = 0
    worker.request_timeout = 0.05

    async def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            await asyncio.sleep(60)
        return response()

    install_transport(monkeypatch, handler)
    worker.error.connect(lambda message, sid: errors.append((message, sid)))
    worker.translation.connect(lambda text, sid: finals.append(sid))
    worker.enqueue("Timeout", 1)
    worker.enqueue("Next", 2)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(finals))
    assert errors == [("翻译超时，本段未完成。", 1)]
    assert finals == [2]


@pytest.mark.parametrize("status", [401, 429, 503])
def test_http_errors_visible_and_not_retried(monkeypatch, qtbot, worker, run_worker, status):
    errors, calls = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "private server detail"}})

    install_transport(monkeypatch, handler)
    worker.error.connect(lambda message, sid: errors.append(message))
    worker.enqueue("Failure", 1)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(errors))
    assert str(status) in errors[0]
    assert "private server detail" not in errors[0]
    assert len(calls) == 1


@pytest.mark.parametrize("parts,finish", [((), "stop"), (("截断",), "length"), (("部分",), None)])
def test_incomplete_stream_is_not_committed(monkeypatch, qtbot, worker, run_worker, parts, finish):
    errors, finals = [], []
    install_transport(monkeypatch, lambda request: response(parts, finish))
    worker.error.connect(lambda message, sid: errors.append(sid))
    worker.translation.connect(lambda text, sid: finals.append(sid))
    worker.enqueue("Incomplete", 1)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(errors))
    assert errors == [1]
    assert not finals
    assert not worker._context


def test_server_error_body_and_credentials_never_reach_logs(monkeypatch, qtbot, worker, run_worker, caplog):
    errors = []
    install_transport(monkeypatch, lambda request: httpx.Response(
        401, json={"error": {"message": "synthetic-private-detail synthetic-secret"}}))
    worker.api_key = "synthetic-secret"
    worker.error.connect(lambda message, sid: errors.append(message))
    worker.enqueue("synthetic-private-transcript", 1)
    run_worker(worker)
    qtbot.waitUntil(lambda: bool(errors))
    visible = caplog.text + " ".join(errors)
    assert "synthetic-private-detail" not in visible
    assert "synthetic-secret" not in visible
    assert "synthetic-private-transcript" not in visible


def test_missing_configuration_stops_cleanly_without_network(monkeypatch, qtbot, run_worker):
    def missing():
        raise MeetingConfigError("Missing private configuration")
    monkeypatch.setattr(module, "load_meeting_config", missing)
    calls, status = [], []
    install_transport(monkeypatch, lambda request: calls.append(request) or response())
    worker = MeetingTranslator(SimpleNamespace(llm_model="", llm_prompt=""))
    worker.status.connect(status.append)
    thread = run_worker(worker)
    qtbot.waitUntil(lambda: bool(status))
    thread.join(1)
    assert not thread.is_alive()
    assert not calls
    assert status == ["Missing private configuration"]
