"""Phrase d'accroche du livre, generee par GABARIT (template NLG).

On remplit une phrase a trous avec les elements deja extraits :
  - titre / auteur : metadonnees extraites du texte brut Gutenberg
  - personnages : --entities
  - lieux : --entities
  - themes : --topics

Aucun modele ne tourne : c'est de la generation par gabarit, donc legere.
"""

from __future__ import annotations

import re

from modules import entities, topics
from utils import metadata

MAX_SUPPORTING_CHARACTERS = 3
MAX_THEMES = 4


def genre(meta: dict) -> str:
    """Premier theme utilisable comme genre dominant."""
    for shelf in re.split(r"[,;]", meta.get("bookshelves", "")):
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


def comparable(value: str) -> str:
    words = re.findall(r"[A-Za-z]+", value.lower())
    return " ".join(words)


def title_location(title: str, locations: list[str]) -> str:
    title_key = comparable(title)
    for location in locations:
        location_key = comparable(location)
        if location_key and location_key in title_key:
            return location
    return ""


def main_place(title: str, locations: list[str]) -> str:
    return title_location(title, locations) or (locations[0] if locations else "")


def _join(items: list[str]) -> str:
    """Joint une liste a l'anglaise : 'a, b and c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def opening_sentence(meta: dict, characters: list[str], place: str, themes: list[str]) -> str:
    title = meta["title"]
    author = meta["authors"]
    main_theme = f"is mainly associated with the theme of {themes[0]}" if themes else ""
    if not characters:
        if main_theme:
            return f"{title}, by {author}, {main_theme}. The book follows a narrative shaped by its characters, places and recurring themes."
        return f"{title}, by {author}, follows a narrative shaped by its characters, places and recurring themes."

    main_character = characters[0]
    supporting = _join(characters[1:1 + MAX_SUPPORTING_CHARACTERS])
    sentence = f'{title}, by {author}, follows {main_character}, the main character,'
    if supporting:
        sentence += f" alongside figures such as {supporting}"
    if place:
        sentence += f", in {place} serving as one of the important places in the story"
    sentence += "."
    return sentence


def themes_sentence(meta: dict, themes: list[str]) -> str:
    if not themes:
        return f'{meta["title"]} presents a narrative that gradually unfolds around the events and relationships encountered throughout the book.'
    return (
        f'{meta["title"]} presents a narrative that gradually unfolds '
        f"around { _join(themes[:MAX_THEMES]) }."
    )


def arc_sentence(book_id: int) -> str:
    arc = section_themes(book_id)
    if len(arc) >= 2 and arc[0] != arc[-1]:
        return f"Across its {len(arc)} chapters, the story moves from {arc[0]} toward {arc[-1]}."
    if arc:
        return f"Across its {len(arc)} chapters, the story centers on {arc[0]}."
    return ""


def build(book_id: int) -> str:
    meta = metadata.info(book_id)
    ent = entities.run(book_id)
    characters = ent.get("characters", [])
    locations = ent.get("locations", [])
    themes = book_themes(book_id)
    place = main_place(meta["title"], locations)

    sentences = [
        opening_sentence(meta, characters, place, themes),
        themes_sentence(meta, themes),
        arc_sentence(book_id),
    ]
    return " ".join(sentence for sentence in sentences if sentence)


def run(book_id: int) -> str:
    return build(book_id)
