from __future__ import annotations
import math
from ahme.compressor import Compressor, SummaryResult


class Merger:
    """Reduces Level-N summaries into a single higher-level summary tree."""

    def __init__(self, batch_size: int) -> None:
        self._batch_size = batch_size

    async def merge(
        self, summaries: list[SummaryResult], level: int, compressor: Compressor
    ) -> SummaryResult:
        """Recursively merge summaries until a single block remains."""
        if len(summaries) == 1:
            return summaries[0]

        # Batch-reduce this level
        reduced: list[SummaryResult] = []
        for i in range(0, len(summaries), self._batch_size):
            batch = summaries[i : i + self._batch_size]
            merged_text = self._summaries_to_text(batch)
            result = await compressor.compress(
                chunk_id=i // self._batch_size,
                text=merged_text,
                level=level,
            )
            result.level = level
            reduced.append(result)

        if len(reduced) == 1:
            return reduced[0]

        # Recurse upward
        return await self.merge(reduced, level=level + 1, compressor=compressor)

    @staticmethod
    def _summaries_to_text(summaries: list[SummaryResult]) -> str:
        return "\n\n---\n\n".join(s.to_text() for s in summaries)
