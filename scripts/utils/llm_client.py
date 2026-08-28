"""Explicit local LLM client configuration.

There are no backend, model, key, timeout, or decoding defaults for the focal paper call.
The prospective focal profile is resolved, but every live value remains explicit and
run-captured.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

def _required(value: str | None, environment_name: str) -> str:
    resolved = value or os.environ.get(environment_name)
    if not resolved:
        raise ValueError(f"Explicit {environment_name} is required; there is no runtime default")
    return resolved


def get_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    *,
    timeout_seconds: float | None = None,
    paper_mode: bool = False,
):
    if timeout_seconds is None:
        raise ValueError("Explicit timeout_seconds is required; there is no runtime default")
    from openai import OpenAI
    return OpenAI(
        base_url=_required(base_url, "LLM_BASE_URL"),
        api_key=_required(api_key, "LLM_API_KEY"),
        timeout=timeout_seconds,
    )


def get_model(model: Optional[str] = None, *, paper_mode: bool = False) -> str:
    return _required(model, "LLM_MODEL")


def chat(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    client: Any | None = None,
    *,
    timeout_seconds: float | None = None,
    paper_mode: bool = False,
) -> Dict:
    if max_tokens is None or temperature is None:
        raise ValueError("Explicit max_tokens and temperature are required")
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    client = client or get_client(
        timeout_seconds=timeout_seconds, paper_mode=paper_mode
    )
    response = client.chat.completions.create(
        model=get_model(model, paper_mode=paper_mode), messages=messages,
        max_tokens=max_tokens, temperature=temperature,
    )
    choice = response.choices[0]
    usage = response.usage
    return {
        "text": choice.message.content or "", "model": response.model,
        "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "finish_reason": choice.finish_reason,
    }
