from __future__ import annotations

from math import ceil
from typing import Any

from sklearn.decomposition import NMF

from modules.cache import load_json, save_json
from modules.nlp import vectorize
from utils.path_config import cache_path, get_text

MIN_SECTIONS = 4
TARGET_TOKENS_PER_SECTION = 1500
MIN_LAST_SECTION_TOKENS = 750
TOPIC_COUNT = 5
TOP_WORDS_PER_TOPIC = 12
CANDIDATE_WORDS_PER_SECTION = 30
CACHE_VERSION = 3
REQUIRED_KEYS = {"version", "method", "topics", "sections", "candidate_count"}
TOPIC_STOP_WORDS = {
    "ll",
    "don",
    "ve",
    "re",
    "chapter",
    "said",
    "say",
    "says",
    "thought",
    "think",
    "know",
    "like",
    "went",
}


def _split_sections(text: str) -> list[str]:
    analyzer = vectorize(stop_words=None).build_analyzer()
    tokens = analyzer(text)
    if not tokens:
        return []

    token_count = len(tokens)
    section_count = max(MIN_SECTIONS, ceil(token_count / TARGET_TOKENS_PER_SECTION))
    remainder = token_count % TARGET_TOKENS_PER_SECTION
    if 0 < remainder < MIN_LAST_SECTION_TOKENS and section_count > MIN_SECTIONS:
        section_count -= 1
    section_size = ceil(len(tokens) / section_count)
    return [
        " ".join(tokens[start:start + section_size])
        for start in range(0, len(tokens), section_size)
    ]


def _candidate_vocabulary(sections: list[str]) -> set[str]:
    if not sections:
        return set()

    vectorizer = vectorize(stop_words="english", extra_stop_words=TOPIC_STOP_WORDS)
    matrix = vectorizer.fit_transform(sections)
    terms = vectorizer.get_feature_names_out()

    candidates = set()
    for row in matrix:
        scores = row.toarray()[0]
        for position in scores.argsort()[::-1][:CANDIDATE_WORDS_PER_SECTION]:
            if scores[position] > 0:
                candidates.add(terms[position])
    return candidates


def _fit_nmf(sections: list[str]) -> dict[str, Any]:
    if not sections:
        return {
            "version": CACHE_VERSION,
            "method": "nmf_tfidf",
            "candidate_count": 0,
            "topics": [],
            "sections": [],
        }

    candidates = _candidate_vocabulary(sections)
    vectorizer = vectorize(
        stop_words="english",
        extra_stop_words=TOPIC_STOP_WORDS,
    )
    if candidates:
        vectorizer.set_params(vocabulary=sorted(candidates))

    matrix = vectorizer.fit_transform(sections)
    terms = vectorizer.get_feature_names_out()

    topic_count = min(TOPIC_COUNT, matrix.shape[0], matrix.shape[1])
    model = NMF(
        n_components=topic_count,
        init="nndsvda",
        random_state=42,
        max_iter=600,
    )
    section_topics = model.fit_transform(matrix)

    topics = []
    for topic_index, weights in enumerate(model.components_):
        total = weights.sum()
        scores = weights / total if total else weights
        ranked = scores.argsort()[::-1]
        words = [
            {"word": terms[position], "score": float(scores[position])}
            for position in ranked[:TOP_WORDS_PER_TOPIC]
            if scores[position] > 0
        ]
        topics.append({
            "topic": topic_index + 1,
            "label": " / ".join(word["word"] for word in words[:3]),
            "words": words,
        })

    section_results = []
    for section_index, topic_weights in enumerate(section_topics):
        total = topic_weights.sum()
        distribution = topic_weights / total if total else topic_weights
        dominant_index = int(distribution.argmax()) if len(distribution) else 0
        section_results.append({
            "section": section_index + 1,
            "token_count": len(sections[section_index].split()),
            "dominant_topic": dominant_index + 1,
            "topic_distribution": [
                {
                    "topic": topic_index + 1,
                    "score": float(score),
                }
                for topic_index, score in enumerate(distribution)
            ],
        })

    return {
        "version": CACHE_VERSION,
        "method": "nmf_tfidf",
        "candidate_count": len(candidates),
        "topics": topics,
        "sections": section_results,
    }


def _compute_topics(text: str) -> dict[str, Any]:
    sections = _split_sections(text)
    return _fit_nmf(sections)


def run(book_id: int) -> dict[str, Any]:
    path = cache_path(book_id, "topics")
    cached = load_json(path, REQUIRED_KEYS)
    if cached is not None:
        return cached

    text = get_text(book_id)
    topics = _compute_topics(text)
    save_json(path, topics)
    return topics
