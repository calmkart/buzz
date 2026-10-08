"""Read meeting API settings only from private files outside the checkout."""

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


class MeetingConfigError(ValueError):
    """A safe, user-facing configuration error without private values."""


@dataclass(frozen=True)
class MeetingConfig:
    api_key: str = field(repr=False)
    base_url: str = field(repr=False)
    model: str = field(repr=False)


def _read_private_file(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as file:
        info = os.fstat(file.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise MeetingConfigError("翻译配置和密钥文件需归当前用户所有，权限设为 600。")
        return file.read(65536).strip()


def load_meeting_config() -> MeetingConfig:
    """No environment or keychain fallback; credentials never enter child envs."""
    try:
        directory = Path.home() / ".token"
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise MeetingConfigError("~/.token 需为当前用户的私有目录，权限设为 700。")
        data = json.loads(_read_private_file(directory / "buzz-teams.json"))
        if not isinstance(data, dict):
            raise ValueError
        base_url, model, key_name = (data.get(key) for key in
                                    ("base_url", "model", "api_key_file"))
        if not all(isinstance(value, str) and value.strip()
                   for value in (base_url, model, key_name)):
            raise ValueError
        if key_name in (".", "..") or Path(key_name).name != key_name:
            raise ValueError
        url = urlsplit(base_url)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.query or url.fragment):
            raise ValueError
        api_key = _read_private_file(directory / key_name)
        if not api_key or any(char.isspace() for char in api_key):
            raise ValueError
        return MeetingConfig(api_key=api_key, base_url=base_url.rstrip("/"), model=model)
    except MeetingConfigError:
        raise
    except (OSError, ValueError, TypeError):
        raise MeetingConfigError(
            "请检查 ~/.token/buzz-teams.json 及其 api_key_file 指定的密钥文件；"
            "需要有效的 HTTPS base_url、model 和密钥。"
        ) from None
