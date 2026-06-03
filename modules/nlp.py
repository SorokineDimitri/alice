from __future__ import annotations

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer

TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z']+\b"


def _stop_words(stop_words: str | None = None, extra_stop_words: set[str] | None = None) -> list[str] | None:
    if stop_words == "english":
        words = set(ENGLISH_STOP_WORDS)
    elif stop_words is None:
        words = None
    else:
        words = set(stop_words)

    if extra_stop_words:
        words = (words or set()) | extra_stop_words

    return sorted(words) if words is not None else None


def vectorize(stop_words: str | None = None, extra_stop_words: set[str] | None = None) -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words=_stop_words(stop_words, extra_stop_words),
        token_pattern=TOKEN_PATTERN,
        norm="l2",
        use_idf=True,
        smooth_idf=True,
    )


def count_vectorize(
    stop_words: str | None = None,
    extra_stop_words: set[str] | None = None,
    max_df: float = 1.0,
) -> CountVectorizer:
    return CountVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words=_stop_words(stop_words, extra_stop_words),
        token_pattern=TOKEN_PATTERN,
        max_df=max_df,
    )
