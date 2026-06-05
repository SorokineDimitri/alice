from __future__ import annotations

import functools
import re
from pathlib import Path

from empath import Empath

from modules.cache import load_json, save_json
from modules.nlp import lemmatize, load_spacy, vectorize
from utils.path_config import cache_path, get_text

THEME_POS = {"NOUN", "PROPN", "ADJ", "VERB"}
TOPIC_WORD_POS = {"NOUN", "PROPN"}
REFERENCE_POS = THEME_POS
WORDS_PER_TOPIC = 10     # combien de mots on garde pour decrire chaque theme
FALLBACK_SECTION_TOKENS = 1500
MAX_SECTION_DF = 0.75

EXPLICIT_HEADING = re.compile(
    r"^\s*(CHAPTER|PART|SECTION)\s+([IVXLCDM]+|\d+)\.?\b.*$",
    re.IGNORECASE,
)
ROMAN_HEADING = re.compile(r"^\s*[IVXLCDM]+\.\s*$")


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
        if section:
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
def empath() -> Empath:
    return Empath()


def reference_words(words: list[str]) -> set[str]:
    nlp = load_spacy(disable=("parser", "ner"))
    references = set()

    for doc in nlp.pipe(word.replace("_", " ") for word in words):
        for token in doc:
            if token.is_stop or not token.is_alpha or token.pos_ not in REFERENCE_POS:
                continue
            references.add(token.lemma_.lower())
    return references


@functools.lru_cache(maxsize=1)
def empath_categories() -> dict[str, set[str]]:
    lexicon = empath()
    return {
        category: reference_words(words)
        for category, words in lexicon.cats.items()
    }


@functools.lru_cache(maxsize=1)
def word_categories() -> dict[str, set[str]]:
    categories_by_word: dict[str, set[str]] = {}
    for category, words in empath_categories().items():
        for word in words:
            categories_by_word.setdefault(word, set()).add(category)
    return categories_by_word


def weighted_words(row, words) -> list[tuple[str, float]]:
    weights = row.toarray()[0]
    positions = weights.argsort()[::-1]
    return [
        (words[position], float(weights[position]))
        for position in positions
        if weights[position] > 0
    ]


def section_theme(words: list[tuple[str, float]]) -> str:
    scores: dict[str, float] = {}
    categories_by_word = word_categories()

    for word, weight in words:
        for category in categories_by_word.get(word, ()):
            scores[category] = scores.get(category, 0.0) + weight

    if not scores:
        return "general"
    return max(scores, key=scores.get)


def noun_topic_words(words: list[tuple[str, float]]) -> set[str]:
    nlp = load_spacy(disable=("parser", "ner"))
    result = set()

    for doc in nlp.pipe(word for word, _ in words):
        for token in doc:
            if token.is_alpha and token.pos_ in TOPIC_WORD_POS:
                result.add(token.lemma_.lower())
    return result


def topic_words(words: list[tuple[str, float]], theme: str) -> list[str]:
    theme_words = empath_categories().get(theme, set())
    noun_words = noun_topic_words(words)
    selected = [
        word for word, _ in words
        if word in theme_words and word in noun_words
    ]

    if len(selected) < WORDS_PER_TOPIC:
        selected_words = set(selected)
        selected.extend(
            word for word, _ in words
            if word not in selected_words and word in noun_words
        )

    return selected[:WORDS_PER_TOPIC]


def max_df_for_sections(sections: list[str]) -> float:
    if len(sections) < 2:
        return 1.0
    return MAX_SECTION_DF


def find_topics(text: str) -> dict[str, dict[str, list[str] | str]]:
    theme_sections = lemmatized_sections(text, keep_pos=THEME_POS)
    if not theme_sections:
        return {}

    theme_vectorizer = vectorize(
        stop_words="english",
        max_df=max_df_for_sections(theme_sections),
    )
    theme_matrix = theme_vectorizer.fit_transform(theme_sections)
    theme_words = theme_vectorizer.get_feature_names_out()

    topics = {}
    for index, theme_row in enumerate(theme_matrix, start=1):
        ranked_theme_words = weighted_words(theme_row, theme_words)
        theme = section_theme(ranked_theme_words)
        topics[str(index)] = {
            "theme": theme,
            "words": topic_words(ranked_theme_words, theme),
        }
    return topics


def valid_cached_topics(payload) -> bool:
    return all(
        isinstance(topic, dict)
        and isinstance(topic.get("theme"), str)
        and isinstance(topic.get("words"), list)
        for topic in payload.values()
    )


def cache_is_current(path) -> bool:
    return path.stat().st_mtime >= Path(__file__).stat().st_mtime


def run(book_id):
    """Point d'entree : renvoie les themes du livre (depuis le cache si possible)."""
    path = cache_path(book_id, "topics")

    cached = load_json(path)
    if cached is not None and cache_is_current(path) and valid_cached_topics(cached):
        return cached

    text = get_text(book_id)
    result = find_topics(text)
    save_json(path, result)
    return result
