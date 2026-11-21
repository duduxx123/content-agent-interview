import asyncio
from content_agent.providers.bilibili import BilibiliLiveProvider
from content_agent.live_window import LiveWindowRunner


async def main() -> None:
    provider = BilibiliLiveProvider.from_env()
    runner = LiveWindowRunner(provider, window_seconds=30)
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
