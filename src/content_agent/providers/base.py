from collections.abc import AsyncIterator
from typing import Protocol

from content_agent.schemas import LiveEvent


class LiveDataProvider(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def next_event(self) -> LiveEvent: ...

    def events(self) -> AsyncIterator[LiveEvent]: ...
