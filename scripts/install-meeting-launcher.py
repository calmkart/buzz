"""Create a local Mac app launcher pointing at this checkout and its uv environment."""
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if not uv or not (root / ".venv/bin/python").exists():
        raise SystemExit("Run uv sync --frozen before creating the launcher.")
    bundle = Path("/Applications/Buzz Teams.app")
    if bundle.is_symlink():
        bundle.unlink()
    contents = bundle / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(exist_ok=True)
    runtime = Path.home() / ".local/share/buzz-teams"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    settings = runtime / "runtime.env"
    settings.touch(mode=0o600, exist_ok=True)
    settings.chmod(0o600)
    settings.write_text(f"BUZZ_PROJECT_DIR={shlex.quote(str(root))}\n"
                        f"BUZZ_UV={shlex.quote(uv)}\n")
    executable = contents / "MacOS/BuzzTeams"
    executable.write_text(
        "#!/bin/zsh\nset -eu\numask 077\n"
        'export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"\n'
        'source "$HOME/.local/share/buzz-teams/runtime.env"\n'
        'mkdir -p "$HOME/Library/Logs/Buzz Teams"\n'
        'cd "$BUZZ_PROJECT_DIR"\n'
        'exec "$BUZZ_UV" run --no-sync python -m buzz.meeting '
        '>> "$HOME/Library/Logs/Buzz Teams/launcher.log" 2>&1\n')
    executable.chmod(0o755)
    info = {
        "CFBundleExecutable": "BuzzTeams",
        "CFBundleIdentifier": "local.buzz.teams",
        "CFBundleName": "Buzz Teams",
        "CFBundleDisplayName": "Buzz Teams",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": tomllib.loads(
            (root / "pyproject.toml").read_text())["project"]["version"],
        "CFBundleIconFile": "buzz.icns",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "读取所选音频输入并生成会议中文字幕。",
    }
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(info, file)
    shutil.copy2(root / "buzz/assets/buzz.icns", contents / "Resources/buzz.icns")
    subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True)
    subprocess.run(["codesign", "--verify", "--strict", str(bundle)], check=True)
    label = "local.buzz.teams.login"
    agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    agent.parent.mkdir(parents=True, exist_ok=True)
    with agent.open("wb") as file:
        plistlib.dump({"Label": label, "ProgramArguments": ["/usr/bin/open", "-g", str(bundle)],
                      "RunAtLoad": True, "LimitLoadToSessionType": "Aqua"}, file)
    agent.chmod(0o644)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    subprocess.run(["launchctl", "enable", f"{domain}/{label}"], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(agent)], check=True)
    (root / "scripts/start-meeting.command").chmod(0o755)
    print("Application launcher:", bundle)
    print("Login startup:", agent)


if __name__ == "__main__":
    main()
