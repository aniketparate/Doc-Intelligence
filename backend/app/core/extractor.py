from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.llm_client import llm_client


EXTRACTION_SYSTEM_PROMPT = """You are a document analyst. Extract structured 
   information from the text below. You MUST return ONLY a valid 
   JSON object with these exact keys:
   document_type, key_dates, key_parties, key_amounts, 
   summary, important_clauses
   
   Rules:
   - Return ONLY the JSON object, no other text
   - Use null for fields not found
   - key_dates, key_parties, key_amounts, important_clauses 
     must be arrays (empty array [] if not found)
   - summary must be a 2-3 sentence string"""

RETRY_INSTRUCTION = (
    "Your previous response was not valid JSON. Return ONLY the raw "
    "JSON object, starting with { and ending with }. No other text."
)

NULL_EXTRACTION_RESULT = {
    "document_type": None,
    "key_dates": None,
    "key_parties": None,
    "key_amounts": None,
    "summary": None,
    "important_clauses": None,
}

MAX_CHUNKS_FOR_EXTRACTION = 20


@dataclass
class ExtractionResult:
    document_type: str | None
    key_dates: list[str] | None
    key_parties: list[str] | None
    key_amounts: list[str] | None
    summary: str | None
    important_clauses: list[str] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "key_dates": self.key_dates,
            "key_parties": self.key_parties,
            "key_amounts": self.key_amounts,
            "summary": self.summary,
            "important_clauses": self.important_clauses,
        }


class Extractor:
    async def extract(self, chunks: list[Any]) -> dict[str, Any]:
        if len(chunks) > MAX_CHUNKS_FOR_EXTRACTION:
            step = max(1, len(chunks) // MAX_CHUNKS_FOR_EXTRACTION)
            chunks = chunks[::step][:MAX_CHUNKS_FOR_EXTRACTION]
        combined_text = self._combine_chunk_text(chunks)
        user_prompt = f"{combined_text}\n\nReturn JSON now."

        response = await llm_client.complete(
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        parsed = self._parse_json(response)
        if parsed is not None:
            return self._normalize_output(parsed)

        retry_prompt = f"{user_prompt}\n\n{RETRY_INSTRUCTION}"
        retry_response = await llm_client.complete(
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": retry_prompt}],
        )

        retry_parsed = self._parse_json(retry_response)
        if retry_parsed is not None:
            return self._normalize_output(retry_parsed)

        return dict(NULL_EXTRACTION_RESULT)

    @staticmethod
    def _combine_chunk_text(chunks: list[Any]) -> str:
        parts: list[str] = []
        for chunk in chunks:
            text = str(getattr(chunk, "window_text", "") or getattr(chunk, "text", "")).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        raw = (text or "").strip()
        if not raw:
            return None

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            candidate = raw[start : end + 1]
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
        def as_string(value: Any) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            return text if text else None

        def as_str_list(value: Any) -> list[str] | None:
            if value is None:
                return None
            if isinstance(value, list):
                out = [str(item).strip() for item in value if str(item).strip()]
                return out if out else []
            single = str(value).strip()
            return [single] if single else []

        result = ExtractionResult(
            document_type=as_string(payload.get("document_type")),
            key_dates=as_str_list(payload.get("key_dates")),
            key_parties=as_str_list(payload.get("key_parties")),
            key_amounts=as_str_list(payload.get("key_amounts")),
            summary=as_string(payload.get("summary")),
            important_clauses=as_str_list(payload.get("important_clauses")),
        )
        return result.to_dict()


extractor = Extractor()
