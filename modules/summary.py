from __future__ import annotations

from pathlib import Path

from modules import entities, lexdiv, overview, topics
from modules.cache import load_json, save_json
from utils import metadata
from utils.path_config import cache_path

SUMMARY_KEY = "summary"
DEPENDENCY_FILES = (
    Path(__file__),
    Path(overview.__file__),
    Path(metadata.__file__),
    Path(entities.__file__),
    Path(lexdiv.__file__),
    Path(topics.__file__),
)


def summarize(book_id: int) -> str:
    return overview.build(book_id)


def cache_is_current(path: Path) -> bool:
    return path.stat().st_mtime >= max(file.stat().st_mtime for file in DEPENDENCY_FILES)


def run(book_id: int) -> str:
    path = cache_path(book_id, "summary")

    cached = load_json(path)
    if (
        cached is not None
        and cache_is_current(path)
        and isinstance(cached.get(SUMMARY_KEY), str)
    ):
        return cached[SUMMARY_KEY]

    summary = summarize(book_id)
    save_json(path, {SUMMARY_KEY: summary})
    return summary
