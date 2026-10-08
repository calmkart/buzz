import asyncio
import threading
from unittest.mock import MagicMock

import httpx
import pytest
from openai import AsyncOpenAI
from PyQt6.QtCore import QObject, pyqtSignal, Qt

from buzz import meeting_translator
from buzz.meeting_config import MeetingConfig
from buzz.settings.settings import Settings
from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget
from buzz.widgets.presentation_window import PresentationWindow


@pytest.fixture
def widget(monkeypatch, qtbot, tmp_path):
    monkeypatch.setenv("BUZZ_MEETING_MODE", "1")
    monkeypatch.setattr(meeting_translator, "load_meeting_config", lambda: MeetingConfig(
        api_key="test-credential", base_url="https://translation.example.invalid/v1", model="test-model"))
    isolated = Settings(application=tmp_path.name)
    class TestSettings(Settings):
        def __new__(cls, *args, **kwargs):
            return isolated
    monkeypatch.setattr("buzz.widgets.recording_transcriber_widget.Settings", TestSettings)
    monkeypatch.setattr("buzz.widgets.transcriber.advanced_settings_dialog.Settings", TestSettings)
    monkeypatch.setattr("buzz.widgets.recording_transcriber_widget.get_password", lambda **kwargs: "")
    monkeypatch.setattr("buzz.widgets.recording_transcriber_widget.RecordingAmplitudeListener", MagicMock())
    monkeypatch.setattr("sounddevice.query_devices", lambda: [
        {"index": 0, "name": "Test audio", "max_input_channels": 1}])
    monkeypatch.setattr("buzz.transcriber.recording_transcriber.RecordingTranscriber.get_device_sample_rate",
                        lambda *args: 16000)
    window = RecordingTranscriberWidget()
    qtbot.addWidget(window)
    window._meeting_accepting = True
    window.transcription_options.enable_llm_translation = True
    window.translator = MagicMock()
    window.export_enabled = False
    yield window
    window.close()
    isolated.clear()


def test_partial_and_final_replace_same_caption_without_duplicate(widget):
    widget.on_next_transcription("Deploy next Tuesday.")
    sid = widget._meeting_segment_id
    widget._on_meeting_partial("下周", sid)
    widget._on_meeting_partial("下周二部署", sid)
    widget._on_meeting_translation("下周二部署。", sid)
    assert widget.translation_text_box.toPlainText() == "下周二部署。"
    widget.on_next_transcription("Keep the GPU allocation.")
    widget._on_meeting_translation("保持 GPU 分配不变。", sid + 1)
    assert widget.translation_text_box.toPlainText() == "下周二部署。\n\n保持 GPU 分配不变。"


def test_stop_marks_partial_cancelled_and_ignores_late_results(widget):
    widget.on_next_transcription("Current sentence.")
    sid = widget._meeting_segment_id
    widget._on_meeting_partial("尚未完成", sid)
    widget.stop_recording()
    assert widget.translation_text_box.toPlainText() == "尚未完成 [已取消]"
    widget._meeting_accepting = True  # A later session cannot accept the old ID.
    widget._on_meeting_translation("旧会话结果", sid)
    assert "旧会话" not in widget.translation_text_box.toPlainText()


def test_only_final_translation_exported(widget):
    widget.export_enabled = True
    widget.translation_export_file = "unused.txt"
    widget.transcript_export_file = ""
    widget.export_file_type = "txt"
    widget.export_max_entries = 0
    widget.write_txt_export = MagicMock()
    widget.on_next_transcription("Sentence.")
    sid = widget._meeting_segment_id
    widget._on_meeting_partial("部", sid)
    widget._on_meeting_partial("部分", sid)
    widget.write_txt_export.assert_not_called()
    widget._on_meeting_translation("完整译文。", sid)
    widget.write_txt_export.assert_called_once()


def test_caption_window_stays_above_teams(monkeypatch, qtbot):
    monkeypatch.setenv("BUZZ_MEETING_MODE", "1")
    window = PresentationWindow()
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


class TestRecorder(QObject):
    __test__ = False
    transcription = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    amplitude_changed = pyqtSignal(float)
    average_amplitude_changed = pyqtSignal(float)
    queue_size_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    audio_dropped = pyqtSignal(int)

    def __init__(self, **kwargs):
        super().__init__()

    def start(self):
        self.transcription.emit("A synthetic meeting sentence.")

    def stop_recording(self):
        self.finished.emit()

    @staticmethod
    def get_device_sample_rate(*args):
        return 16000


def test_close_cancels_network_and_waits_for_both_qthreads(widget, monkeypatch, qtbot):
    entered = threading.Event()

    async def handler(request):
        entered.set()
        await asyncio.sleep(60)

    def client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False))

    monkeypatch.setattr(meeting_translator, "AsyncOpenAI", client)
    monkeypatch.setattr("buzz.widgets.recording_transcriber_widget.RecordingTranscriber", TestRecorder)
    widget.translator = None
    widget.current_status = widget.RecordingStatus.RECORDING
    widget.show()
    widget.on_model_loaded("synthetic-model")
    qtbot.waitUntil(entered.is_set, timeout=5000)
    widget.close()
    qtbot.waitUntil(lambda: widget.transcription_thread is None and
                   widget.translation_thread is None, timeout=3000)
    assert not widget.isVisible()
