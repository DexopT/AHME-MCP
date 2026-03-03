from __future__ import annotations
import json
import httpx
from dataclasses import dataclass, field


_SYSTEM_PROMPT = """You are a memory compression assistant.
Given a conversation chunk, output ONLY valid JSON with these keys:
- key_facts: list of important facts (strings)
- decisions: list of decisions or conclusions reached
- open_questions: list of unresolved questions
- entities: list of key named entities (people, tools, concepts)
Respond with nothing but the JSON object. No markdown, no explanation."""


@dataclass
class SummaryResult:
    chunk_id: int
    level: int
    key_facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        parts = []
        if self.key_facts:
            parts.append("Key facts: " + "; ".join(self.key_facts))
        if self.decisions:
            parts.append("Decisions: " + "; ".join(self.decisions))
        if self.open_questions:
            parts.append("Open questions: " + "; ".join(self.open_questions))
        if self.entities:
            parts.append("Entities: " + ", ".join(self.entities))
        return "\n".join(parts)


class Compressor:
    """Sends chunks to a local Ollama model and returns structured summaries."""

    def __init__(self, base_url: str, model: str, timeout: int) -> None:
        self._model = model
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def compress(self, chunk_id: int, text: str, level: int) -> SummaryResult:
        payload = {
            "model": self._model,
            "prompt": text,
            "system": _SYSTEM_PROMPT,
            "stream": False,
        }

        # Retry with backoff — Ollama can disconnect while loading the model
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = await self._client.post("/api/generate", json=payload)
                resp.raise_for_status()
                raw = resp.json()["response"]
                break
            except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as exc:
                last_err = exc
                import asyncio
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
        else:
            raise last_err  # type: ignore[misc]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: treat entire response as a single fact
            data = {"key_facts": [raw], "decisions": [], "open_questions": [], "entities": []}

        return SummaryResult(
            chunk_id=chunk_id,
            level=level,
            key_facts=data.get("key_facts", []),
            decisions=data.get("decisions", []),
            open_questions=data.get("open_questions", []),
            entities=data.get("entities", []),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
