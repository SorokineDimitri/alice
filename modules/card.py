from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from modules import entities, lexdiv, similarity, summary, topics
from modules.cache import load_json, save_json
from modules.cleaner import START_MARKER
from utils.path_config import cache_path, get_raw_text

REQUIRED_KEYS = {"info", "lexdiv", "topics", "entities", "summary", "similar"}
BOOKSHELF_LIMIT = 5
AUTHOR_PREFIX = re.compile(r"^_?\s*(by|author)\s*:?\s*_?\s*(.*)$", re.IGNORECASE)
IGNORED_AUTHOR_MARKERS = {"by the same author"}
HEADER_END = re.compile(
    r"^(contents|chapter|letter|part|section|dramatis personae)\b",
    re.IGNORECASE,
)
DEPENDENCY_FILES = (
    Path(__file__),
    Path(lexdiv.__file__),
    Path(topics.__file__),
    Path(entities.__file__),
    Path(summary.__file__),
    Path(similarity.__file__),
)


def clean_line(line: str) -> str:
    return " ".join(line.strip().strip("_ ").split())


def book_header(text: str) -> str:
    start = text.find(START_MARKER)
    if start == -1:
        return text

    line_end = text.find("\n", start)
    if line_end == -1:
        return ""
    return text[line_end + 1:]


def useful_lines(text: str) -> list[str]:
    lines = []
    for line in book_header(text).splitlines():
        cleaned = clean_line(line)
        if cleaned and HEADER_END.match(cleaned):
            break
        if cleaned:
            lines.append(cleaned)
    return lines


def author_from_marker(lines: list[str], index: int, value: str) -> str:
    if value:
        return clean_line(value)
    if index + 1 < len(lines):
        return clean_line(lines[index + 1])
    if index > 0:
        return clean_line(lines[index - 1])
    return ""


def ignored_author_marker(line: str) -> bool:
    return line.lower() in IGNORED_AUTHOR_MARKERS


def find_author(text: str) -> str:
    lines = useful_lines(text)
    for index, line in enumerate(lines):
        match = AUTHOR_PREFIX.match(line)
        if match and not ignored_author_marker(line):
            return author_from_marker(lines, index, match.group(2))
    return ""


def bookshelves_from_topics(book_id: int) -> str:
    counts = Counter(topics.topic_themes(book_id))
    return "; ".join(
        theme for theme, _ in counts.most_common(BOOKSHELF_LIMIT)
    )


def numbered_topics(book_id: int) -> dict[str, list[str]]:
    result = {}
    for key, words in topics.run(book_id).items():
        number = key.split(": ", 1)[0]
        result[number] = words
    return result


def info(book_id: int) -> dict[str, str]:
    return {
        "id": str(book_id),
        "authors": find_author(get_raw_text(book_id)),
        "bookshelves": bookshelves_from_topics(book_id),
    }


def similar_titles(book_id: int) -> list[str]:
    similarity.prepare(book_id)
    return similarity.run(book_id)


def build_card(book_id: int) -> dict:
    return {
        "info": info(book_id),
        "lexdiv": lexdiv.run(book_id),
        "topics": numbered_topics(book_id),
        "entities": entities.run(book_id),
        "summary": summary.run(book_id),
        "similar": similar_titles(book_id),
    }


def valid_info(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
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
