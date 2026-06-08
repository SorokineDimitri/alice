
from __future__ import annotations

import re
from math import ceil

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from modules.cache import load_json, save_json
from modules.nlp import load_spacy, spacy_chunks, vectorize
from utils.path_config import cache_path, get_text

SUMMARY_SENTENCES = 5      # nombre de phrases dans le resume final
MIN_SENTENCE_WORDS = 12    # on ignore les phrases courtes (repliques type "said Alice")
MAX_SENTENCES = 4000       # plafond pour borner la memoire/temps sur les gros livres
QUOTE_FRACTION_MAX = 0.20  # au-dela, la phrase est surtout du dialogue -> ecartee
MAX_DF = 0.3               # ignore les mots ultra-frequents ("said", noms de persos)
DAMPING = 0.85             # facteur d'amortissement de PageRank
ITERATIONS = 50            # nombre d'iterations de PageRank

_QUOTED = re.compile(r"[“\"][^”\"]*[”\"]")

SHORTEN_MAX_WORDS = 16  # longueur max d'une puce de resume (lisibilite)
# Connecteurs a ne pas laisser en FIN de puce tronquee (sinon "...gone, and").
_TAIL_DROP = {
    "and", "but", "or", "so", "as", "when", "while", "which", "that", "for",
    "nor", "yet", "then", "with", "of", "in", "on", "to", "by", "at",
    "a", "an", "the",
}

def is_clean_sentence(sentence):
    """Ecarte les phrases mal formees pour un resume lisible."""
    # Doit commencer par une majuscule, sinon c'est un fragment mal decoupe
    # (ex. "the Sheep said at last...").
    first_letter = next((char for char in sentence if char.isalpha()), "")
    if not first_letter.isupper():
        return False
    # Guillemets equilibres : un nombre impair = dialogue coupe en plein milieu
    # (ex. 'So she began: "O Mouse, do you know...').
    if (sentence.count("“") + sentence.count("”") + sentence.count('"')) % 2 != 0:
        return False
    return True


def split_sentences(text):
    nlp = load_spacy(disable=("ner", "tagger", "lemmatizer", "attribute_ruler"))

    sentences = []
    for chunk in spacy_chunks(text):  # un livre peut depasser la limite spaCy
        for sent in nlp(chunk).sents:
            cleaned = " ".join(sent.text.split())
            if len(cleaned.split()) >= MIN_SENTENCE_WORDS and is_clean_sentence(cleaned):
                sentences.append(cleaned)
    return sentences[:MAX_SENTENCES]


def shorten(sentence):
    """Tronque une phrase a sa proposition principale, pour des puces lisibles.

    Les phrases classiques mettent l'action au debut, puis elaborent apres
    un ':' ou ';'. On garde le debut (l'essentiel) et on coupe le reste.
    """
    # 1) couper a la premiere frontiere forte (deux-points, point-virgule, tiret)
    cut = len(sentence)
    for separator in (":", ";", "—"):
        position = sentence.find(separator)
        if position != -1:
            cut = min(cut, position)
    head = sentence[:cut].strip()

    # 2) si encore trop long, reculer a la derniere virgule avant la limite
    words = head.split()
    if len(words) > SHORTEN_MAX_WORDS:
        head = " ".join(words[:SHORTEN_MAX_WORDS])
        comma = head.rfind(",")
        if comma > 10:
            head = head[:comma]

    # 3) ne pas finir sur un connecteur ("...gone, and")
    parts = head.rstrip(" ,;:—.").split()
    while parts and parts[-1].lower().strip(",") in _TAIL_DROP:
        parts.pop()
    head = " ".join(parts).rstrip(" ,;:—.")

    # 4) "..." si on a vraiment coupe du texte
    suffix = "..." if len(head) < len(sentence.rstrip(".")) - 3 else ""
    return head + suffix


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
    picks = []
    for start in range(0, len(sentences), size):
        block = sentences[start:start + size]
        if block:
            picks.append(best_sentence(block))
    return picks



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
    return [sentences[index] for index in chosen]



def pick_sentences(text, method="textrank"):
    """Renvoie la LISTE des phrases retenues (une par bloc chronologique)."""
    sentences = narrative_sentences(split_sentences(text))
    if len(sentences) <= SUMMARY_SENTENCES:
        return sentences
    if method == "clustering":
        return summarize_clustering(sentences)
    return summarize_textrank(sentences)


def summarize(text, method="textrank"):
    return " ".join(pick_sentences(text, method))


def run(book_id):
    path = cache_path(book_id, "summary")

    cached = load_json(path)
    if cached is not None and "summary" in cached:
        return cached["summary"]


    # Accroche par gabarit (de quoi parle le livre) + passages extractifs.
    # Le resume est presente en liste a puces (1 phrase/ligne, ordre du livre)
    # pour etre lisible plutot qu'un pave de texte.
    from modules import overview
    opener = overview.build(book_id)
    picks = pick_sentences(get_text(book_id))
    body = "\n".join(f"- {shorten(sentence)}" for sentence in picks)
    summary = f"{opener}\n\n--- Résumé ---\n{body}"

    save_json(path, {"summary": summary})
    return summary
