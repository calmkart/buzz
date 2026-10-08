from unittest.mock import MagicMock

import numpy as np

from buzz.transcriber.recording_transcriber import RecordingTranscriber
from buzz.transcriber.transcriber import TranscriptionOptions


def make_recorder():
    return RecordingTranscriber(TranscriptionOptions(transcription_step=3.5),
                                input_device_index=0, sample_rate=16000,
                                model_path="unused", sounddevice=MagicMock())


def test_meeting_uses_configured_nonoverlapping_audio_window(monkeypatch, qtbot):
    monkeypatch.setenv("BUZZ_MEETING_MODE", "1")
    recorder = make_recorder()
    assert recorder.n_batch_samples == 56000
    assert recorder.transcriber_mode.name == "APPEND_BELOW"
    monkeypatch.delenv("BUZZ_MEETING_MODE")
    ordinary = make_recorder()
    assert ordinary.n_batch_samples == 80000


def test_audio_overload_is_visible_without_flooding_ui(monkeypatch, qtbot):
    monkeypatch.setenv("BUZZ_MEETING_MODE", "1")
    recorder = make_recorder()
    recorder.queue = np.zeros(recorder.max_queue_size, dtype=np.float32)
    dropped = []
    recorder.audio_dropped.connect(dropped.append)
    for _ in range(10):
        recorder.stream_callback(np.ones((160, 1), dtype=np.float32), 160, None, None)
    assert dropped == [160]
    assert recorder.queue.size == recorder.max_queue_size
