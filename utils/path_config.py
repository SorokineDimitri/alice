from __future__ import annotations

from pathlib import Path

RAW_DIR = Path("data/raw")
CACHE_DIR = Path("data/cache")


def raw_path(book_id: int) -> Path:
    return RAW_DIR / f"{book_id}.txt"


def cache_path(book_id: int, task: str) -> Path:
    return CACHE_DIR / f"{book_id}_{task}.json"
