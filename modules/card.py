from __future__ import annotations

from modules import entities, lexdiv, similarity, summary, topics
from modules.cache import load_json, save_json
from utils import metadata
from utils.path_config import cache_path

REQUIRED_KEYS = {"info", "lexdiv", "topics", "entities", "summary", "similar"}


def similar_titles(book_id: int, force: bool = False) -> list[str]:
    similarity.prepare(book_id)
    return similarity.run(book_id, force=force)


def build_card(book_id: int, force: bool = False) -> dict:
    return {
        "info": metadata.info(book_id, force=force),
        "lexdiv": lexdiv.run(book_id, force=force),
        "topics": topics.run(book_id, force=force),
        "entities": entities.run(book_id, force=force),
        "summary": summary.run(book_id, force=force),
        "similar": similar_titles(book_id, force=force),
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


def run(book_id: int, force: bool = False) -> dict:
    path = cache_path(book_id, "card")
    cached = load_json(path, REQUIRED_KEYS)
    if not force and cached is not None and valid_cached_card(cached):
        return cached

    result = build_card(book_id, force=force)
    save_json(path, result)
    return result
