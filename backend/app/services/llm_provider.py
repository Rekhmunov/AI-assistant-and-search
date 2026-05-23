from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class SearchSource:
    index: int
    url: str
    title: str
    snippet: str
    domain: str


class LLMProvider(ABC):
    @abstractmethod
    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        ...
