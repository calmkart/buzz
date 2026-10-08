"""Download the small.en Whisper.cpp/CoreML model used by the Teams trial."""
from buzz.model_loader import ModelDownloader, TranscriptionModel, ModelType, WhisperModelSize


def main():
    model = TranscriptionModel(model_type=ModelType.WHISPER_CPP,
                               whisper_model_size=WhisperModelSize.SMALLEN)
    existing = model.get_local_model_path()
    if existing:
        print("Meeting ASR model ready:", existing)
        return 0
    results, errors = [], []
    downloader = ModelDownloader(model=model)
    downloader.signals.finished.connect(results.append)
    downloader.signals.error.connect(lambda message: errors.append(True))
    downloader.run()
    print("Meeting ASR model ready:", bool(results) and not errors)
    return 0 if results and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
