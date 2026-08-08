from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings


QA_SYSTEM_PROMPT_TEMPLATE = (
    "You are an expert document analyst. Answer STRICTLY from the\n"
    "context below.\n"
    "Rules:\n"
    "1. Only use information explicitly in the provided context.\n"
    "2. If not found, say 'Not found in documents.'\n"
    "3. Copy numbers, dates, and names exactly as written.\n"
    "4. You have memory of this conversation — use it to resolve\n"
    "   follow-up questions and pronouns.\n"
    "{summary_block}\n"
    "Document Context:\n"
    "{retrieved_context}"
)


class LLMClient:
    def __init__(self) -> None:
        self._backend = settings.LLM_BACKEND.lower()
        self._ollama_base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._vllm_base_url = str(getattr(settings, "VLLM_BASE_URL", "http://localhost:8001")).rstrip("/")
        self._model = settings.LLM_MODEL
        self._default_temperature = settings.LLM_TEMPERATURE
        self._max_tokens = settings.LLM_MAX_TOKENS

    async def complete(self, system: str, messages: list[dict], temperature: float = None) -> str:
        if self._backend == "ollama":
            return await self._complete_ollama(system=system, messages=messages, temperature=temperature)
        if self._backend == "vllm":
            return await self._complete_vllm(system=system, messages=messages, temperature=temperature)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unsupported LLM backend: {self._backend}")

    async def generate(self, system_prompt: str, user_prompt: str, temperature: float = None) -> str:
        return await self.complete(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )

    async def chat(self, system_prompt: str, user_prompt: str, temperature: float = None) -> str:
        return await self.generate(system_prompt=system_prompt, user_prompt=user_prompt, temperature=temperature)

    async def _complete_ollama(self, system: str, messages: list[dict], temperature: float = None) -> str:
        merged_messages = self._merge_messages(system=system, messages=messages)

        payload = {
            "model": self._model,
            "messages": merged_messages,
            "stream": False,
            "options": {
                "temperature": self._resolve_temperature(temperature),
                "num_predict": self._max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        message = data.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid Ollama response format")
        return content.strip()

    async def _complete_vllm(self, system: str, messages: list[dict], temperature: float = None) -> str:
        merged_messages = self._merge_messages(system=system, messages=messages)

        payload = {
            "model": self._model,
            "messages": merged_messages,
            "temperature": self._resolve_temperature(temperature),
            "max_tokens": self._max_tokens,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(f"{self._vllm_base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid vLLM response format")

        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid vLLM response message")
        return content.strip()

    def build_qa_system_prompt(self, summary_block: str, retrieved_context: str) -> str:
        return QA_SYSTEM_PROMPT_TEMPLATE.format(
            summary_block=summary_block or "",
            retrieved_context=retrieved_context or "",
        )

    @staticmethod
    def _merge_messages(system: str, messages: list[dict]) -> list[dict]:
        merged: list[dict[str, str]] = []
        if system.strip():
            merged.append({"role": "system", "content": system.strip()})

        for message in messages:
            role = str(message.get("role", "user")).strip() or "user"
            content = str(message.get("content", "")).strip()
            merged.append({"role": role, "content": content})

        return merged

    def _resolve_temperature(self, temperature: float | None) -> float:
        return self._default_temperature if temperature is None else float(temperature)


llm_client = LLMClient()
