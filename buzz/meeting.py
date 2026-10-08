"""Launch Buzz's live recording UI with a separate Teams trial profile."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def main():
    os.environ["BUZZ_MEETING_MODE"] = "1"
    os.environ["BUZZ_APP_NAME"] = "Buzz Teams"
    os.environ["BUZZ_DISABLE_TELEMETRY"] = "1"
    os.environ["BUZZ_DISABLE_UPDATE_CHECK"] = "1"

    from platformdirs import user_log_dir
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from buzz.assets import get_path
    from buzz.meeting_config import load_meeting_config, MeetingConfigError
    from buzz.meeting_translator import TRANSLATION_PROMPT
    from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
    from buzz.settings.settings import Settings
    from buzz.transcriber.transcriber import Task
    from buzz.widgets.recording_transcriber_widget import RecordingTranscriberWidget

    log_dir = Path(user_log_dir("Buzz Teams"))
    os.umask(0o077)
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir.chmod(0o700)
    handler = RotatingFileHandler(log_dir / "meeting.log", maxBytes=2_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    app = QApplication(sys.argv)
    app.setApplicationName("Buzz Teams")
    app.setWindowIcon(QIcon(get_path("assets/buzz.ico")))
    try:
        config = load_meeting_config()
    except MeetingConfigError as exc:
        QMessageBox.warning(None, "翻译配置", str(exc))
        return 1

    settings = Settings()
    if not settings.value(Settings.Key.MEETING_PROFILE_INITIALIZED, False):
        defaults = {
            Settings.Key.RECORDING_TRANSCRIBER_MODEL: TranscriptionModel(
                model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.SMALLEN),
            Settings.Key.RECORDING_TRANSCRIBER_LANGUAGE: "en",
            Settings.Key.RECORDING_TRANSCRIBER_TASK: Task.TRANSCRIBE,
            Settings.Key.RECORDING_TRANSCRIBER_MODE: 0,
            Settings.Key.RECORDING_TRANSCRIBER_TRANSCRIPTION_STEP: 3.5,
            Settings.Key.RECORDING_TRANSCRIBER_ENABLE_LLM_TRANSLATION: True,
            Settings.Key.RECORDING_TRANSCRIBER_LLM_PROMPT: TRANSLATION_PROMPT,
            Settings.Key.RECORDING_TRANSCRIBER_EXPORT_ENABLED: False,
            Settings.Key.PRESENTATION_WINDOW_THEME: "dark",
            Settings.Key.PRESENTATION_WINDOW_TEXT_SIZE: 22,
            Settings.Key.MEETING_PROFILE_INITIALIZED: True,
        }
        for name, value in defaults.items():
            settings.set_value(name, value)

    window = RecordingTranscriberWidget()
    window.transcription_options.llm_model = config.model
    window.transcription_options_group_box.advanced_settings_dialog.llm_model_line_edit.setText(config.model)
    for index, (_, name) in enumerate(window.audio_devices_combo_box.audio_devices):
        if "BlackHole 2ch" in name:
            window.audio_devices_combo_box.setCurrentIndex(index)
            break
    else:
        window.meeting_status_label.setText(
            "未检测到 BlackHole 2ch。Teams 桌面声音需要先配置系统音频路由；"
            "也可选择麦克风测试识别。")
    window.resize(1000, 760)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
