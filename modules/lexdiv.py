from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from modules.gutenberg import download

RAW_DIR = Path("data/raw")
CACHE_DIR = Path("data/cache")

REQUIRED_KEYS = {"tok", "typ", "hap", "ttr", "mwl", "mwf"}


def _raw_path(book_id: int) -> Path:
    return RAW_DIR / f"{book_id}.txt"


def _cache_path(book_id: int) -> Path:
    return CACHE_DIR / f"{book_id}_lexdiv.json"


def _load_cached(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not REQUIRED_KEYS.issubset(payload.keys()):
        return None
    return payload


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_or_fetch_text(book_id: int) -> str:
    path = _raw_path(book_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8")

    text = download(book_id)
    path.write_text(text, encoding="utf-8")
    return text


def _compute_metrics(text: str) -> dict[str, float | int]:
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z']+\b",
        norm="l2",
        use_idf=True,
        smooth_idf=True,
    )
    vectorizer.fit_transform([text])
    analyzer = vectorizer.build_analyzer()
    tokens = analyzer(text)
    frequencies = Counter(tokens)

    tok = sum(frequencies.values())
    typ = len(frequencies)
    hap = sum(1 for count in frequencies.values() if count == 1)
    ttr = (typ / tok) if tok else 0.0
    mwl = (sum(len(token) for token in tokens) / tok) if tok else 0.0
    mwf = (tok / typ) if typ else 0.0

    return {
        "tok": tok,
        "typ": typ,
        "hap": hap,
        "ttr": ttr,
        "mwl": mwl,
        "mwf": mwf,
    }


def run(book_id: int) -> dict[str, float | int]:
    cache_path = _cache_path(book_id)
    cached = _load_cached(cache_path)
    if cached is not None:
        return cached

    text = _load_or_fetch_text(book_id)
    metrics = _compute_metrics(text)
    _save_cache(cache_path, metrics)
    return metrics
