from __future__ import annotations

import re
from collections import Counter

from modules import topics
from modules.cleaner import START_MARKER
from utils.path_config import get_raw_text

BOOKSHELF_LIMIT = 5
AUTHOR_PREFIX = re.compile(r"^_?\s*(by|author)\s*:?\s*_?\s*(.*)$", re.IGNORECASE)
HEADER_END = re.compile(
    r"^(contents|chapter|letter|part|section|dramatis personae)\b",
    re.IGNORECASE,
)
IGNORED_AUTHOR_MARKERS = {"by the same author"}
IGNORED_TITLE_LINES = {
    "[illustration]",
    "[illustrations]",
}


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


def ignored_title_line(line: str) -> bool:
    return line.lower() in IGNORED_TITLE_LINES


def find_title(text: str) -> str:
    title_lines = []
    for line in useful_lines(text):
        match = AUTHOR_PREFIX.match(line)
        if match and not ignored_author_marker(line):
            break
        if ignored_author_marker(line) or ignored_title_line(line):
            continue
        title_lines.append(line)
    return " ".join(title_lines)


def bookshelves_from_topics(book_id: int) -> str:
    counts = Counter(topics.topic_themes(book_id))
    return "; ".join(
        theme for theme, _ in counts.most_common(BOOKSHELF_LIMIT)
    )


def info(book_id: int) -> dict[str, str]:
    text = get_raw_text(book_id)
    return {
        "id": str(book_id),
        "title": find_title(text),
        "authors": find_author(text),
        "bookshelves": bookshelves_from_topics(book_id),
    }


def run(book_id: int) -> dict[str, str]:
    return info(book_id)
