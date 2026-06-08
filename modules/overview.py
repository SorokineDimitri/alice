"""Phrase d'accroche du livre, generee par GABARIT (template NLG).

On remplit une phrase a trous (toujours grammaticale, car ecrite a la main)
avec les elements deja extraits :
  - titre / auteur : metadonnees RDF Gutenberg (--metadata)
  - personnages : --entities
  - themes : --topics

Aucun modele ne tourne : c'est de la generation par gabarit, donc legere.

Limite assumee : la phrase herite de la qualite des slots. Si --entities se
trompe de personnage, la phrase sera fluide mais fausse ("garbage in, out").
On n'inclut PAS les lieux : le decor est deja dans le titre ("...in
Wonderland"), et le NER confond lieux cites au passage et vrai cadre fictif.
"""

from __future__ import annotations

from modules import entities, lexdiv, metadata, topics

MAX_CHARACTERS = 4
MAX_THEMES = 4


def genre(meta: dict) -> str:
    """Premier rayon (bookshelf) utilisable comme genre, ex. 'Horror'."""
    for shelf in meta.get("bookshelves", "").split(","):
        shelf = shelf.strip()
        if shelf and not shelf.lower().startswith("category"):
            return shelf
    return ""


def section_themes(book_id: int) -> list[str]:
    """Themes section par section, DANS L'ORDRE (avec doublons)."""
    return [
        key.split(": ", 1)[1].strip()
        for key in topics.run(book_id)
        if ": " in key
    ]


def book_themes(book_id: int) -> list[str]:
    """Themes uniques du livre (sans doublons, ordre d'apparition)."""
    result = []
    for theme in section_themes(book_id):
        if theme and theme not in result:
            result.append(theme)
    return result


def _join(items: list[str]) -> str:
    """Joint une liste a l'anglaise : 'a, b and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def build(book_id: int) -> str:
    meta = metadata.run(book_id)
    ent = entities.run(book_id)
    characters = _join(ent.get("characters", [])[:MAX_CHARACTERS])
    themes = _join(book_themes(book_id)[:MAX_THEMES])
    book_genre = genre(meta)

    # Phrase 1 : identite (titre, auteur, genre).
    first = f"{meta['title']}, by {meta['authors']},"
    first += f" is a work of {book_genre}." if book_genre else " is a classic."

    # Phrase 2 : contenu (personnages, themes).
    second = ""
    if characters:
        second = f" It follows {characters}"
        if themes:
            second += f" in a tale of {themes}"
        second += "."
    elif themes:
        second = f" It is a tale of {themes}."

    # Phrase 3 : echelle concrete (chiffres fiables issus de --lexdiv).
    stats = lexdiv.run(book_id)
    tok = stats.get("tok", 0)
    typ = stats.get("typ", 0)
    third = (
        f" The book spans about {tok:,} words drawn from a vocabulary "
        f"of {typ:,} distinct terms."
    )

    # Phrase 4 : arc thematique (themes du debut vers la fin, par chapitre).
    arc = section_themes(book_id)
    if len(arc) >= 2 and arc[0] != arc[-1]:
        fourth = (
            f" Across its {len(arc)} chapters, the story moves from "
            f"{arc[0]} toward {arc[-1]}."
        )
    elif arc:
        fourth = f" Across its {len(arc)} chapters, it centers on {arc[0]}."
    else:
        fourth = ""

    # Phrase 5 : style (longueur moyenne des mots, mots rares — via --lexdiv).
    mwl = stats.get("mwl", 0.0)
    hap = stats.get("hap", 0)
    fifth = (
        f" Its prose averages {mwl:.1f} characters per word, with {hap:,} "
        f"words used only once."
    )

    return first + second + third + fourth + fifth


def run(book_id: int) -> str:
    return build(book_id)
