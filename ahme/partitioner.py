from __future__ import annotations
import tiktoken


class Partitioner:
    """Splits raw text into token-accurate overlapping chunks."""

    def __init__(self, chunk_size_tokens: int, overlap_tokens: int) -> None:
        if overlap_tokens >= chunk_size_tokens:
            overlap_tokens = max(0, chunk_size_tokens // 10)
        self._chunk_size = chunk_size_tokens
        self._overlap = overlap_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    def partition(self, text: str) -> list[str]:
        if not text.strip():
            return []

        token_ids = self._enc.encode(text)
        chunks: list[str] = []
        step = self._chunk_size - self._overlap
        # Guard: step must be at least 1 to avoid infinite loop
        step = max(1, step)

        i = 0
        while i < len(token_ids):
            window = token_ids[i : i + self._chunk_size]
            chunks.append(self._enc.decode(window))
            if i + self._chunk_size >= len(token_ids):
                break
            i += step

        return chunks
