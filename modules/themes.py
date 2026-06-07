

from __future__ import annotations

from empath import Empath

# Categories trop generiques pour faire un theme parlant : on les ignore.
SKIP = {
    "speaking", "communication", "listen", "hearing",
    "reading", "writing",
    "social_media", "phone", "computer", "internet",
    "positive_emotion", "negative_emotion",
}

# On charge le lexique une seule fois (au chargement du module).
_lexicon = Empath()


def label_section(text):
    """Renvoie le theme dominant d'un texte (ou 'indetermine')."""
    scores = _lexicon.analyze(text, normalize=True)
    if not scores:
        return "indetermine"

    # On enleve les categories generiques et les scores nuls.
    scores = {
        category: score
        for category, score in scores.items()
        if category not in SKIP and score > 0
    }
    if not scores:
        return "indetermine"

    # La categorie au plus gros score = le theme qui domine la section.
    return max(scores, key=scores.get)


def label_sections(sections_text):
    """Attribue un theme a chaque section.

    sections_text : liste de textes (une chaine par section).
    Retour        : liste de themes (un par section, meme ordre).
    """
    return [label_section(text) for text in sections_text]
