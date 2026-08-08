from __future__ import annotations

from app.config import settings
from app.core.llm_client import llm_client


HYDE_SYSTEM_PROMPT = (
    "Generate a short factual paragraph that would answer "
    "the following question. Write it as if it appears in "
    "a document. Be concise and specific."
)


class HyDE:
    async def generate_hypothesis(self, question: str) -> str:
        if not settings.HYDE_ENABLED:
            return question

        hypothesis = await llm_client.complete(
            system=HYDE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        return hypothesis.strip() or question


hyde = HyDE()
