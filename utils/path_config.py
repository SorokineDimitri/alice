from __future__ import annotations

from pathlib import Path

from modules.cleaner import clean
from modules.gutenberg import download

RAW_DIR = Path("data/raw")
CACHE_DIR = Path("data/cache")


def raw_path(book_id: int) -> Path:
    return RAW_DIR / f"{book_id}.txt"


def cache_path(book_id: int, task: str) -> Path:
    return CACHE_DIR / f"{book_id}_{task}.json"


def get_text(book_id: int) -> str:
    path = raw_path(book_id)

    if path.exists():
        raw = path.read_text(encoding="utf-8")
    else:
        raw = download(book_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")

    return clean(raw)
