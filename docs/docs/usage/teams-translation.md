# Buzz Teams 实时中文字幕

会议模式使用本地语音识别，再通过用户配置的 OpenAI 兼容接口翻译为简体中文。
源码、示例和测试不包含真实服务地址、模型部署名或凭据。

## 启动与私有配置

打开 `/Applications/Buzz Teams.app`。安装程序会为当前用户设置登录自启动；
启动只打开界面，点击录音后才采集音频。此应用是源码启动器，需要保留安装时使用的源码目录和虚拟环境。

配置文件为 `~/.token/buzz-teams.json`，格式如下（全部为占位示例）：

```json
{
  "base_url": "https://translation.example.invalid/v1",
  "model": "your-model-id",
  "api_key_file": "buzz-teams-api-key"
}
```

将实际密钥保存在 `~/.token/` 下由 `api_key_file` 指定的文件内，只放密钥本身。
目录权限为 `700`，配置和密钥文件权限为 `600`，均归当前用户所有；不接受符号链接。
配置中的地址必须使用 HTTPS。应用不再从环境变量或钥匙串读取翻译密钥，也不将密钥传入子进程环境。
高级设置允许临时调整翻译模型，下次启动仍以私有配置为准。

源码启动方式：

```sh
uv run --no-sync python -m buzz.meeting
```

## Teams 音频设置

1. 安装 BlackHole 2ch，按安装器提示重启电脑。
2. 在 macOS“音频 MIDI 设置”中创建多输出设备，同时勾选扬声器/耳机和 BlackHole 2ch。
3. 以实际播放设备为主设备，为另一个设备启用漂移校正，保持相同采样率，例如 48 kHz。设备可命名为 **Teams + Buzz**。
4. 在 Teams 的设备设置中，将扬声器设为该多输出设备，麦克风保持实际使用的麦克风。
5. Buzz 音频输入选择 **BlackHole 2ch**，点击录音；可另开置顶字幕窗口。

改用耳机时，相应更新多输出设备中的播放设备。

## 行为与限制

- 默认使用 Whisper.cpp / small.en、English、Transcribe；语音分块默认 3.5 秒。
- 翻译流式显示，单段最多 512 个 completion tokens；仅保留最近三个已完成双语片段作为请求上下文。
- 请求总时限 20 秒，最多等待 6 段，等待超过 15 秒时显示跳过提示。
- 停止后取消在途及待处理翻译，保留已显示的部分并标记未完成。
- 默认不导出会议记录；显式启用导出后才保存文本。日志不记录翻译请求、响应正文或凭据。
- 断句、识别速度和远端服务耗时共同影响字幕延迟；合成测试不能代替实际会议验证。

## 安装与验证

```sh
git submodule update --init --depth 1
uv sync --frozen
uv run --no-sync python scripts/prepare-meeting-model.py
uv run --no-sync python scripts/install-meeting-launcher.py
uv run --no-sync python scripts/check-meeting-api.py
```

安装脚本写入 `/Applications/Buzz Teams.app` 和当前用户的
`~/Library/LaunchAgents/local.buzz.teams.login.plist`，只在登录时启动一次。
源码路径和 uv 路径保存于源码以外的 `~/.local/share/buzz-teams/runtime.env`。
关闭窗口会正常退出，不会自动重启。原有 Buzz 文件转录入口保持不变。

本地测试：

```sh
BUZZ_DISABLE_TELEMETRY=1 QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/meeting_config_test.py tests/meeting_translator_test.py tests/meeting_audio_test.py tests/widgets/meeting_recording_test.py tests/translator_test.py
```

本地调试截图、录音、日志和私有配置不应放进源码仓库或发布包。
