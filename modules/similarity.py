from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path
from typing import Any

from requests import RequestException
from sklearn.metrics.pairwise import cosine_similarity

from modules.cache import load_json, save_json
from modules.gutenberg import download
from modules.nlp import vectorize
from utils.path_config import cache_path, get_text, raw_path

SIMILAR_LIMIT = 5
DOWNLOAD_CONCURRENCY = 4
CATEGORY_BONUS = 0.15
BOOK_LIST_PATH = Path(__file__).resolve().parent.parent / "data" / "similar_books.json"
SIMILAR_CACHE_KEY = "similar"


@functools.lru_cache(maxsize=1)
def book_catalog() -> dict[int, dict[str, str]]:
    payload = json.loads(BOOK_LIST_PATH.read_text(encoding="utf-8"))
    return {
        book["id"]: {
            "title": book.get("title", str(book["id"])),
            "category": book.get("category", ""),
        }
        for book in payload
        if isinstance(book, dict) and isinstance(book.get("id"), int)
    }


def similar_books() -> dict[int, str]:
    return {
        book_id: book["title"]
        for book_id, book in book_catalog().items()
    }


def similar_book_ids() -> list[int]:
    return sorted(book_catalog())


def corpus_book_ids(book_id: int) -> list[int]:
    ids = set(similar_book_ids())
    ids.add(book_id)
    return sorted(ids)


async def cache_book(book_id: int, semaphore: asyncio.Semaphore) -> bool:
    path = raw_path(book_id)
    if path.exists():
        return True

    async with semaphore:
        try:
            raw = await asyncio.to_thread(download, book_id)
        except (RuntimeError, RequestException):
            return False

        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, raw, encoding="utf-8")
        return True


async def cache_books(book_ids: list[int]) -> set[int]:
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    results = await asyncio.gather(
        *(cache_book(book_id, semaphore) for book_id in book_ids)
    )
    return {
        book_id for book_id, available in zip(book_ids, results)
        if available
    }


def available_texts(book_ids: list[int]) -> dict[int, str]:
    texts = {}
    for book_id in book_ids:
        try:
            texts[book_id] = get_text(book_id)
        except (RuntimeError, RequestException):
            continue
    return texts


def same_category_bonus(book_id: int, candidate_id: int) -> float:
    catalog = book_catalog()
    target = catalog.get(book_id, {})
    candidate = catalog.get(candidate_id, {})
    if not target or not candidate:
        return 0.0
    return CATEGORY_BONUS if target.get("category") == candidate.get("category") else 0.0


def rank_similar(book_id: int, texts: dict[int, str]) -> list[int]:
    if book_id not in texts:
        raise RuntimeError(f"Livre {book_id} introuvable")

    ids = list(texts)
    documents = [texts[candidate_id] for candidate_id in ids]
    matrix = vectorize(stop_words="english").fit_transform(documents)
    target_index = ids.index(book_id)
    lexical_scores = cosine_similarity(matrix[target_index], matrix).ravel()

    ranked = sorted(
        (
            (
                ids[index],
                float(score) + same_category_bonus(book_id, ids[index]),
            )
            for index, score in enumerate(lexical_scores)
            if ids[index] != book_id
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return [candidate_id for candidate_id, _ in ranked[:SIMILAR_LIMIT]]


def prepare(book_id: int) -> set[int]:
    return asyncio.run(cache_books(corpus_book_ids(book_id)))


def valid_cached_similarity(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get(SIMILAR_CACHE_KEY), list)
        and len(payload[SIMILAR_CACHE_KEY]) <= SIMILAR_LIMIT
        and all(isinstance(title, str) for title in payload[SIMILAR_CACHE_KEY])
    )


def run(book_id: int, force: bool = False) -> list[str]:
    path = cache_path(book_id, "similar")
    cached = load_json(path)
    if not force and cached is not None and valid_cached_similarity(cached):
        return cached[SIMILAR_CACHE_KEY]

    texts = available_texts(corpus_book_ids(book_id))
    titles = similar_books()
    result = [
        titles.get(candidate_id, str(candidate_id))
        for candidate_id in rank_similar(book_id, texts)
    ]
    save_json(path, {SIMILAR_CACHE_KEY: result})
    return result
