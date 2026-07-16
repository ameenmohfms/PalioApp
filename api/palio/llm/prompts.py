"""Loader for versioned prompt assets in /prompts (spec §5).

Prompts are code: they live in the repo, go through review, and changes must
keep the eval suite green. Conversational agents compose _base.md + their
kernel; sentinel prompts are standalone (they never speak with Palio's voice).
"""

from functools import lru_cache
from pathlib import Path

from palio.config import get_settings


class PromptMissing(RuntimeError):
    pass


@lru_cache(maxsize=32)
def load(name: str) -> str:
    path = Path(get_settings().prompts_dir) / f"{name}.md"
    if not path.is_file():
        raise PromptMissing(f"prompt asset not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PromptMissing(f"prompt asset empty: {path}")
    return text


def composed(agent: str) -> str:
    """base + agent kernel, for the conversational agents (Phase 2+)."""
    return load("_base") + "\n\n---\n\n" + load(agent)
