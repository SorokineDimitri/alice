from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from modules.cache import load_json, save_json
from modules.nlp import lemmatize, vectorize
from utils.path_config import cache_path, get_text

THEME_POS = {"NOUN", "PROPN", "ADJ", "VERB"}
WORDS_PER_TOPIC = 10     # combien de mots on garde pour decrire chaque theme
FALLBACK_SECTION_TOKENS = 1500
MAX_SECTION_DF = 0.3
MIN_SECTION_WORDS = 80
THEMES_PATH = Path(__file__).resolve().parent.parent / "data" / "literary_themes.json"

EXPLICIT_HEADING = re.compile(
    r"^\s*(CHAPTER|PART|SECTION)\s+([IVXLCDM]+|\d+)\.?\b.*$",
    re.IGNORECASE,
)
ROMAN_HEADING = re.compile(r"^\s*[IVXLCDM]+\.\s*$")
WORD = re.compile(r"[A-Za-z]+")
TOPIC_KEY = re.compile(r"^\d+: .+$")


def split_chunks(words: list[str], chunk_size: int) -> list[str]:
    return [
        " ".join(words[start:start + chunk_size])
        for start in range(0, len(words), chunk_size)
    ]


def split_from_headings(text: str, pattern: re.Pattern[str]) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if pattern.match(line)]
    if len(starts) < 2:
        return []

    sections = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        section = "\n".join(lines[start + 1:end]).strip()
        if len(WORD.findall(section)) >= MIN_SECTION_WORDS:
            sections.append(section)
    return sections


def author_sections(text: str) -> list[str]:
    for pattern in (EXPLICIT_HEADING, ROMAN_HEADING):
        sections = split_from_headings(text, pattern)
        if sections:
            return sections
    return []


def lemmatized_sections(text: str, keep_pos: set[str]) -> list[str]:
    sections = author_sections(text)
    if sections:
        return [
            section
            for section in (lemmatize(section, keep_pos=keep_pos) for section in sections)
            if section
        ]

    lemmas = lemmatize(text, keep_pos=keep_pos).split()
    return split_chunks(lemmas, FALLBACK_SECTION_TOKENS)


@functools.lru_cache(maxsize=1)
def theme_dictionary() -> dict[str, set[str]]:
    payload = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    return {
        theme: {
            word.lower()
            for word in words
            if isinstance(word, str) and word.isalpha()
        }
        for theme, words in payload.items()
        if isinstance(theme, str) and isinstance(words, list)
    }


def weighted_words(row, words) -> list[tuple[str, float]]:
    weights = row.toarray()[0]
    positions = weights.argsort()[::-1]
    return [
        (words[position], float(weights[position]))
        for position in positions
        if weights[position] > 0
    ]


def theme_score(words: list[tuple[str, float]], theme_words: set[str]) -> float:
    return sum(weight for word, weight in words if word in theme_words)


def best_theme(words: list[tuple[str, float]]) -> str:
    themes = theme_dictionary()
    if not themes:
        return "general"

    theme, score = max(
        (
            (theme, theme_score(words, theme_words))
            for theme, theme_words in themes.items()
        ),
        key=lambda item: item[1],
    )
    return theme if score > 0 else "general"


def topic_words(words: list[tuple[str, float]], theme: str) -> list[str]:
    theme_words = theme_dictionary().get(theme, set())
    selected = [
        word for word, _ in words
        if word in theme_words
    ]

    if len(selected) < WORDS_PER_TOPIC:
        selected_words = set(selected)
        selected.extend(
            word for word, _ in words
            if word not in selected_words
        )

    return selected[:WORDS_PER_TOPIC]


def max_df_for_sections(sections: list[str]) -> float:
    if len(sections) < 2:
        return 1.0
    return MAX_SECTION_DF


def topic_key(index: int, theme: str) -> str:
    return f"{index}: {theme}"


def theme_from_key(key: str) -> str:
    if ": " not in key:
        return ""
    return key.split(": ", 1)[1]


def find_topics(text: str) -> dict[str, list[str]]:
    sections = lemmatized_sections(text, keep_pos=THEME_POS)
    if not sections:
        return {}

    theme_vectorizer = vectorize(
        stop_words="english",
        max_df=max_df_for_sections(sections),
    )
    theme_matrix = theme_vectorizer.fit_transform(sections)
    words = theme_vectorizer.get_feature_names_out()

    topics = {}
    for index, row in enumerate(theme_matrix, start=1):
        ranked_words = weighted_words(row, words)
        theme = best_theme(ranked_words)
        topics[topic_key(index, theme)] = topic_words(ranked_words, theme)
    return topics


def valid_cached_topics(payload) -> bool:
    return (
        isinstance(payload, dict)
        and all(
            isinstance(section, str)
            and bool(TOPIC_KEY.match(section))
            and isinstance(topic, list)
            and len(topic) == WORDS_PER_TOPIC
            and all(isinstance(word, str) for word in topic)
            for section, topic in payload.items()
        )
    )


def run(book_id, force: bool = False):
    """Point d'entree : renvoie les themes du livre (depuis le cache si possible)."""
    path = cache_path(book_id, "topics")

    cached = load_json(path)
    if not force and cached is not None and valid_cached_topics(cached):
        return cached

    text = get_text(book_id)
    result = find_topics(text)
    save_json(path, result)
    return result


def topic_themes(book_id: int, force: bool = False) -> list[str]:
    return [
        theme
        for theme in (theme_from_key(key) for key in run(book_id, force=force))
        if theme
    ]
