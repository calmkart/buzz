"""Run one synthetic translation; never log credentials or request headers."""
import asyncio
import time

from openai import AsyncOpenAI

from buzz.meeting_config import load_meeting_config, MeetingConfigError
from buzz.meeting_translator import TRANSLATION_PROMPT, quiet_api_logging


async def main():
    quiet_api_logging()
    try:
        config = load_meeting_config()
    except MeetingConfigError as exc:
        print(str(exc))
        return 2
    try:
        async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url,
                               max_retries=0, timeout=20) as client:
            started = time.monotonic()
            stream = await client.chat.completions.create(
                model=config.model,
                messages=[{"role": "system", "content": TRANSLATION_PROMPT},
                          {"role": "user", "content": "The library opens at nine tomorrow morning."}],
                max_completion_tokens=512, stream=True)
            text, first, finish = "", None, None
            async with stream:
                async for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        finish = choice.finish_reason or finish
                        if choice.delta.content:
                            first = first or time.monotonic()
                            text += choice.delta.content
            print("Synthetic translation received:", bool(text))
            print("First output seconds:", round((first or started) - started, 2),
                  "complete seconds:", round(time.monotonic() - started, 2),
                  "finish:", finish)
            return 0 if text and finish == "stop" else 1
    except Exception as exc:
        print("API check failed:", type(exc).__name__,
              "HTTP status:", getattr(exc, "status_code", None))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
