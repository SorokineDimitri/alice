from __future__ import annotations

import asyncio
import functools
import json
from pathlib import Path

from requests import RequestException
from sklearn.metrics.pairwise import cosine_similarity

from modules.cache import load_json, save_json
from modules.gutenberg import download
from modules.nlp import vectorize
from utils.path_config import cache_path, get_text, raw_path

SIMILAR_LIMIT = 5
DOWNLOAD_CONCURRENCY = 4
BOOK_LIST_PATH = Path(__file__).resolve().parent.parent / "data" / "similar_books.json"
SIMILAR_CACHE_KEY = "similar"


@functools.lru_cache(maxsize=1)
def similar_books() -> dict[int, str]:
    payload = json.loads(BOOK_LIST_PATH.read_text(encoding="utf-8"))
    return {
        book["id"]: book.get("title", str(book["id"]))
        for book in payload
        if isinstance(book, dict) and isinstance(book.get("id"), int)
    }


def similar_book_ids() -> list[int]:
    return sorted(similar_books())


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


def rank_similar(book_id: int, texts: dict[int, str]) -> list[int]:
    if book_id not in texts:
        raise RuntimeError(f"Livre {book_id} introuvable")

    ids = list(texts)
    documents = [texts[candidate_id] for candidate_id in ids]
    matrix = vectorize(stop_words="english").fit_transform(documents)
    target_index = ids.index(book_id)
    scores = cosine_similarity(matrix[target_index], matrix).ravel()

    ranked = sorted(
        (
            (ids[index], float(score))
            for index, score in enumerate(scores)
            if ids[index] != book_id
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return [candidate_id for candidate_id, _ in ranked[:SIMILAR_LIMIT]]


def prepare(book_id: int) -> set[int]:
    return asyncio.run(cache_books(corpus_book_ids(book_id)))


def valid_cached_similarity(payload) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get(SIMILAR_CACHE_KEY), list)
        and len(payload[SIMILAR_CACHE_KEY]) <= SIMILAR_LIMIT
        and all(isinstance(title, str) for title in payload[SIMILAR_CACHE_KEY])
    )


def run(book_id: int) -> list[str]:
    path = cache_path(book_id, "similar")
    cached = load_json(path)
    if cached is not None and valid_cached_similarity(cached):
        return cached[SIMILAR_CACHE_KEY]

    texts = available_texts(corpus_book_ids(book_id))
    titles = similar_books()
    result = [
        titles.get(candidate_id, str(candidate_id))
        for candidate_id in rank_similar(book_id, texts)
    ]
    save_json(path, {SIMILAR_CACHE_KEY: result})
    return result
