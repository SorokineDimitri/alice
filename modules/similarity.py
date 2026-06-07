from __future__ import annotations

from requests import RequestException
from sklearn.metrics.pairwise import cosine_similarity

from modules.nlp import vectorize
from utils.path_config import RAW_DIR, get_text

SIMILAR_LIMIT = 5

def raw_book_ids() -> list[int]:
    return sorted(
        int(path.stem)
        for path in RAW_DIR.glob("*.txt")
        if path.stem.isdigit()
    )


def corpus_book_ids(book_id: int) -> list[int]:
    ids = set(raw_book_ids())
    ids.add(book_id)
    return sorted(ids)


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
    matrix = vectorize(stop_words="english").fit_transform(texts[book_id] for book_id in ids)
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


def run(book_id: int) -> list[int]:
    texts = available_texts(corpus_book_ids(book_id))
    return rank_similar(book_id, texts)
