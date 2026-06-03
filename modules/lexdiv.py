from __future__ import annotations

from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer

from modules.cache import load_json, save_json
from modules.gutenberg import download
from utils.path_config import cache_path, raw_path

REQUIRED_KEYS = {"tok", "typ", "hap", "ttr", "mwl", "mwf"}


def _load_or_fetch_text(book_id: int) -> str:
    path = raw_path(book_id)
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
    path = cache_path(book_id, "lexdiv")
    cached = load_json(path, REQUIRED_KEYS)
    if cached is not None:
        return cached

    text = _load_or_fetch_text(book_id)
    metrics = _compute_metrics(text)
    save_json(path, metrics)
    return metrics
