from __future__ import annotations

from modules import overview
from modules.cache import load_json, save_json
from utils.path_config import cache_path

SUMMARY_KEY = "summary"


def summarize(book_id: int, force: bool = False) -> str:
    return overview.build(book_id, force=force)


def run(book_id: int, force: bool = False) -> str:
    path = cache_path(book_id, "summary")

    cached = load_json(path)
    if not force and cached is not None and isinstance(cached.get(SUMMARY_KEY), str):
        return cached[SUMMARY_KEY]

    summary = summarize(book_id, force=force)
    save_json(path, {SUMMARY_KEY: summary})
    return summary
