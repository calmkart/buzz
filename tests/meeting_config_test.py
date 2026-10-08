import json
import os
from pathlib import Path

import pytest

from buzz.meeting_config import load_meeting_config, MeetingConfigError


@pytest.fixture
def private_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    directory = tmp_path / ".token"
    directory.mkdir(mode=0o700)
    key = directory / "test-key"
    key.write_text("synthetic-secret\n")
    key.chmod(0o600)
    path = directory / "buzz-teams.json"
    path.write_text(json.dumps({"base_url": "https://translation.example.invalid/v1",
                                "model": "test-model", "api_key_file": key.name}))
    path.chmod(0o600)
    return directory, path, key


def test_private_files_supply_config_without_exposing_or_exporting_values(private_config):
    before = dict(os.environ)
    config = load_meeting_config()
    assert config.api_key == "synthetic-secret"
    assert config.base_url == "https://translation.example.invalid/v1"
    assert config.model == "test-model"
    assert repr(config) == "MeetingConfig()"
    assert dict(os.environ) == before


@pytest.mark.parametrize("index,mode", [(0, 0o755), (1, 0o644), (2, 0o644)])
def test_rejects_files_or_directory_readable_by_other_users(private_config, index, mode):
    private_config[index].chmod(mode)
    with pytest.raises(MeetingConfigError):
        load_meeting_config()


@pytest.mark.parametrize("index", [0, 1, 2])
def test_rejects_symlinked_private_storage(private_config, index):
    path = private_config[index]
    actual = path.with_name(path.name + "-actual")
    path.rename(actual)
    path.symlink_to(actual, target_is_directory=index == 0)
    with pytest.raises(MeetingConfigError):
        load_meeting_config()


@pytest.mark.parametrize("field,value", [
    ("base_url", "http://translation.example.invalid/v1"),
    ("base_url", "https://user:synthetic-secret@translation.example.invalid/v1"),
    ("base_url", "https://translation.example.invalid/v1?key=synthetic-secret"),
    ("api_key_file", "../test-key"),
    ("api_key_file", "/tmp/test-key"),
    ("model", ""),
])
def test_invalid_configuration_has_a_safe_error(private_config, field, value):
    path = private_config[1]
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(MeetingConfigError) as error:
        load_meeting_config()
    assert "synthetic-secret" not in str(error.value)
    assert "example.invalid" not in str(error.value)


def test_missing_file_does_not_fall_back_to_environment(private_config, monkeypatch):
    monkeypatch.setenv("BUZZ_TRANSLATION_API_KEY", "synthetic-secret")
    private_config[2].unlink()
    with pytest.raises(MeetingConfigError):
        load_meeting_config()


def test_malformed_json_does_not_echo_contents(private_config):
    private_config[1].write_text('{"secret": "synthetic-secret"')
    with pytest.raises(MeetingConfigError) as error:
        load_meeting_config()
    assert "synthetic-secret" not in str(error.value)
