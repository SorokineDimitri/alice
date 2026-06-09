from __future__ import annotations

from pathlib import Path

from modules import entities, lexdiv, similarity, summary, topics
from modules.cache import load_json, save_json
from utils import metadata
from utils.path_config import cache_path

REQUIRED_KEYS = {"info", "lexdiv", "topics", "entities", "summary", "similar"}
DEPENDENCY_FILES = (
    Path(__file__),
    Path(metadata.__file__),
    Path(lexdiv.__file__),
    Path(topics.__file__),
    Path(entities.__file__),
    Path(summary.__file__),
    Path(similarity.__file__),
)


def similar_titles(book_id: int) -> list[str]:
    similarity.prepare(book_id)
    return similarity.run(book_id)


def build_card(book_id: int) -> dict:
    return {
        "info": metadata.info(book_id),
        "lexdiv": lexdiv.run(book_id),
        "topics": topics.run(book_id),
        "entities": entities.run(book_id),
        "summary": summary.run(book_id),
        "similar": similar_titles(book_id),
    }


def valid_info(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and isinstance(value.get("title"), str)
        and isinstance(value.get("authors"), str)
        and isinstance(value.get("bookshelves"), str)
    )


def valid_cached_card(payload) -> bool:
    return (
        isinstance(payload, dict)
        and REQUIRED_KEYS.issubset(payload)
        and valid_info(payload.get("info"))
        and isinstance(payload.get("lexdiv"), dict)
        and isinstance(payload.get("topics"), dict)
        and isinstance(payload.get("entities"), dict)
        and isinstance(payload.get("summary"), str)
        and isinstance(payload.get("similar"), list)
    )


def cache_is_current(path: Path) -> bool:
    return path.stat().st_mtime >= max(file.stat().st_mtime for file in DEPENDENCY_FILES)


def run(book_id: int) -> dict:
    path = cache_path(book_id, "card")
    cached = load_json(path, REQUIRED_KEYS)
    if cached is not None and cache_is_current(path) and valid_cached_card(cached):
        return cached

    result = build_card(book_id)
    save_json(path, result)
    return result
