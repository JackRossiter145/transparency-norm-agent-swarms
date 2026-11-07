"""Thin wrapper around the Adaption client that tracks spend across threads."""

import threading
from pathlib import Path

from adaption import Adaption
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class LLM:
    def __init__(self, max_retries: int = 4):
        self.client = Adaption(max_retries=max_retries)
        self.total_cost = 0.0
        self.calls = 0
        self._lock = threading.Lock()

    def chat(
        self,
        model: str,
        instructions: str,
        messages: list[dict],
        max_output_tokens: int = 400,
        temperature: float = 0.7,
    ) -> str:
        """One stateless call: system `instructions` + an alternating user/assistant history."""
        r = self.client.responses.create(
            model=model,
            instructions=instructions,
            input=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            store=False,
        )
        cost = getattr(getattr(r, "usage", None), "cost", None) or 0.0
        with self._lock:
            self.total_cost += cost
            self.calls += 1
        return (r.output_text or "").strip()
