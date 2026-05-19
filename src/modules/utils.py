"""Small shared helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Iterator, TypeVar

import yaml


T = TypeVar("T")


_FENCE_RE = re.compile(r"^\s*```(?:json|yaml|yml)?\s*|\s*```\s*$", re.IGNORECASE)


def strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` style fences that LLMs (esp. Gemini) sometimes emit."""
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json|yaml|yml)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```\s*$", "", stripped)
    return stripped.strip()


def parse_json_safe(text: str) -> Any:
    """Parse JSON, stripping markdown fences if present."""
    return json.loads(strip_json_fences(text))


def to_yaml(data: Any) -> str:
    """Serialise to YAML. Used when client requests response_format=yaml."""
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def chunk(items: Iterable[T], size: int) -> Iterator[list[T]]:
    buf: list[T] = []
    for item in items:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
