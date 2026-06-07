
from __future__ import annotations

import re
from math import ceil

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from modules.cache import load_json, save_json
from modules.nlp import load_spacy, spacy_chunks, vectorize
from utils.path_config import cache_path, get_text

SUMMARY_SENTENCES = 7      # nombre de phrases dans le resume final
MIN_SENTENCE_WORDS = 12    # on ignore les phrases courtes (repliques type "said Alice")
MAX_SENTENCES = 4000       # plafond pour borner la memoire/temps sur les gros livres
QUOTE_FRACTION_MAX = 0.20  # au-dela, la phrase est surtout du dialogue -> ecartee
MAX_DF = 0.3               # ignore les mots ultra-frequents ("said", noms de persos)
DAMPING = 0.85             # facteur d'amortissement de PageRank
ITERATIONS = 50            # nombre d'iterations de PageRank

_QUOTED = re.compile(r"[“\"][^”\"]*[”\"]")

def split_sentences(text):
    nlp = load_spacy(disable=("ner", "tagger", "lemmatizer", "attribute_ruler"))

    sentences = []
    for chunk in spacy_chunks(text):  # un livre peut depasser la limite spaCy
        for sent in nlp(chunk).sents:
            cleaned = " ".join(sent.text.split())
            if len(cleaned.split()) >= MIN_SENTENCE_WORDS:
                sentences.append(cleaned)
    return sentences[:MAX_SENTENCES]


def quote_fraction(sentence):
    quoted = _QUOTED.findall(sentence)
    return sum(len(part) for part in quoted) / max(len(sentence), 1)


def narrative_sentences(sentences):
    narrative = [s for s in sentences if quote_fraction(s) < QUOTE_FRACTION_MAX]
    return narrative if len(narrative) >= SUMMARY_SENTENCES else sentences


# --------------------------------------------------------------------------
# Methode 1 : TextRank (retenue)
# --------------------------------------------------------------------------
def textrank_scores(similarity):
    n = similarity.shape[0]
    np.fill_diagonal(similarity, 0.0)

    row_sums = similarity.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    transition = similarity / row_sums

    scores = np.full(n, 1.0 / n)
    for _ in range(ITERATIONS):
        scores = (1.0 - DAMPING) / n + DAMPING * (transition.T @ scores)
    return scores


def best_sentence(block):
    if len(block) == 1:
        return block[0]
    try:
        matrix = vectorize(stop_words="english", max_df=MAX_DF).fit_transform(block)
        scores = textrank_scores(cosine_similarity(matrix))
        return block[int(np.argmax(scores))]
    except ValueError:
        return max(block, key=len)


def summarize_textrank(sentences):
    size = ceil(len(sentences) / SUMMARY_SENTENCES)
    summary = []
    for start in range(0, len(sentences), size):
        block = sentences[start:start + size]
        if block:
            summary.append(best_sentence(block))
    return " ".join(summary)



def summarize_clustering(sentences):
    matrix = vectorize(stop_words="english", max_df=MAX_DF).fit_transform(sentences)
    kmeans = KMeans(n_clusters=SUMMARY_SENTENCES, random_state=42, n_init=10)
    labels = kmeans.fit_predict(matrix)

    chosen = []
    for cluster in range(SUMMARY_SENTENCES):
        members = [i for i, label in enumerate(labels) if label == cluster]
        if not members:
            continue
        center = kmeans.cluster_centers_[cluster].reshape(1, -1)
        similarities = cosine_similarity(matrix[members], center).ravel()
        chosen.append(members[int(similarities.argmax())])

    chosen.sort()  # ordre chronologique pour la lisibilite
    return " ".join(sentences[index] for index in chosen)



def summarize(text, method="textrank"):
    sentences = narrative_sentences(split_sentences(text))
    if len(sentences) <= SUMMARY_SENTENCES:
        return " ".join(sentences)
    if method == "clustering":
        return summarize_clustering(sentences)
    return summarize_textrank(sentences)


def run(book_id):
    path = cache_path(book_id, "summary")

    cached = load_json(path)
    if cached is not None and "summary" in cached:
        return cached["summary"]

    summary = summarize(get_text(book_id))
    save_json(path, {"summary": summary})
    return summary
