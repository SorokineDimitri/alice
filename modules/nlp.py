from __future__ import annotations
import functools
from sklearn.feature_extraction.text import TfidfVectorizer

TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z']+\b"
SPACY_MAX_LEN = 1_000_000  # limite de caracteres par appel spaCy


def vectorize(
    stop_words: str | None = None,
    max_df: float = 1.0,
) -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        stop_words=stop_words,
        token_pattern=TOKEN_PATTERN,
        max_df=max_df,
        norm="l2",
        use_idf=True,
        smooth_idf=True,
    )


@functools.lru_cache(maxsize=1)
def _nlp():
    import spacy

    # parser et ner inutiles ici : pipeline plus leger, on garde tagger+lemmatizer.
    return spacy.load("en_core_web_sm", disable=["parser", "ner"])


def _spacy_chunks(text: str):
    for start in range(0, len(text), SPACY_MAX_LEN):
        yield text[start:start + SPACY_MAX_LEN]


def lemmatize(text: str, keep_pos: set[str]) -> str:
    """Reduit le texte a ses lemmes porteurs de sens (noms, adjectifs, verbes).

    spaCy gere les contractions (don't -> do/not) et la flexion (came -> come),
    ce qui supprime le besoin de listes de stop words bricolees a la main.
    """
    nlp = _nlp()
    lemmas: list[str] = []
    for chunk in _spacy_chunks(text):  # un livre peut depasser la limite spaCy
        for token in nlp(chunk):
            if token.is_stop or token.is_punct or token.is_space:
                continue
            if not token.is_alpha or token.pos_ not in keep_pos:
                continue
            lemmas.append(token.lemma_.lower())
    return " ".join(lemmas)
