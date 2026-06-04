from __future__ import annotations

from collections import Counter

from modules.cache import load_json, save_json
from modules.nlp import load_spacy, spacy_chunks
from utils.path_config import cache_path, get_text

CONTEXT_WINDOW = 4
ACTION_POS = {"VERB", "AUX"}
CHARACTER_DEPS = {"nsubj", "dobj", "pobj", "attr", "appos", "conj"}
LOCATION_POS = {"ADP"}
POSSESSIVE_MARKERS = {"'s", "’s"}
OWNER_POS = {"PROPN", "NOUN", "ADJ"}
LOCATION_PHRASE_POS = {"PROPN", "NOUN", "ADJ"}
PERSON_NOUNS = {
    "baby",
    "cat",
    "child",
    "cook",
    "duchess",
    "duck",
    "footman",
    "gryphon",
    "hare",
    "hatter",
    "king",
    "knave",
    "lizard",
    "majesty",
    "man",
    "mouse",
    "pigeon",
    "queen",
    "rabbit",
    "turtle",
    "witness",
}
LOCATION_NOUNS = {
    "bank",
    "brook",
    "castle",
    "court",
    "field",
    "forest",
    "garden",
    "ground",
    "hall",
    "house",
    "kitchen",
    "palace",
    "path",
    "pool",
    "river",
    "room",
    "shore",
    "shop",
    "square",
    "street",
    "table",
    "wood",
}


def normalize_entity(name: str) -> str:
    return " ".join(name.split()).strip(".,;:!?\"'“”‘’")


def clean_phrase(tokens) -> str:
    phrase = " ".join(token.text for token in tokens)
    phrase = phrase.replace(" 's ", "'s ")
    phrase = phrase.replace(" ’s ", "’s ")
    phrase = phrase.replace(" - ", "-")
    return normalize_entity(phrase)


def context_tokens(entity):
    start = max(0, entity.start - CONTEXT_WINDOW)
    end = min(len(entity.doc), entity.end + CONTEXT_WINDOW)
    for token in entity.doc[start:end]:
        if token.i < entity.start or token.i >= entity.end:
            yield token


def context_bonus(entity, group: str) -> int:
    tokens = context_tokens(entity)
    if group == "characters":
        return int(any(token.pos_ in ACTION_POS for token in tokens))
    if group == "locations":
        return int(any(token.pos_ in LOCATION_POS for token in tokens))
    return 0


def has_character_context(entity) -> bool:
    return entity.root.dep_ in CHARACTER_DEPS and entity.root.head.pos_ == "VERB"


def has_location_context(entity) -> bool:
    return any(token.pos_ in LOCATION_POS for token in context_tokens(entity))


def owner_tokens(doc, possessive_index: int):
    tokens = []
    for index in range(possessive_index - 1, -1, -1):
        token = doc[index]
        if token.lower_ == "of" or token.pos_ in OWNER_POS:
            tokens.append(token)
            continue
        break
    return list(reversed(tokens))


def location_tokens(doc, possessive_index: int):
    tokens = []
    for token in doc[possessive_index + 1:possessive_index + 6]:
        if token.text == "-" and tokens:
            tokens.append(token)
            continue
        if token.pos_ not in LOCATION_PHRASE_POS:
            break
        tokens.append(token)
    return tokens


def is_location_phrase(tokens) -> bool:
    return any(token.lemma_.lower() in LOCATION_NOUNS for token in tokens)


def is_person_phrase(tokens) -> bool:
    return any(token.lemma_.lower() in PERSON_NOUNS for token in tokens)


def entity_group(entity):
    if entity.label_ == "PERSON" and (
        has_character_context(entity) or is_person_phrase(entity)
    ):
        return "characters"
    if entity.label_ == "GPE" and has_location_context(entity):
        return "locations"
    if entity.label_ in {"LOC", "FAC"} and is_location_phrase(entity):
        return "locations"
    return None


def possessive_locations(doc):
    for token in doc:
        if token.text not in POSSESSIVE_MARKERS:
            continue

        owner = owner_tokens(doc, token.i)
        location = location_tokens(doc, token.i)
        if not owner or not location or not is_location_phrase(location):
            continue

        phrase = clean_phrase(owner + [token] + location)
        if phrase:
            yield phrase


def find_entities(text: str) -> dict[str, list[str]]:
    nlp = load_spacy()
    counters = {
        "characters": Counter(),
        "locations": Counter(),
    }

    for doc in nlp.pipe(spacy_chunks(text)):
        for entity in doc.ents:
            group = entity_group(entity)
            if group is None:
                continue
            name = normalize_entity(entity.text)
            if name:
                counters[group][name] += 1 + context_bonus(entity, group)
        for location in possessive_locations(doc):
            counters["locations"][location] += 2

    return {
        group: [name for name, _ in counter.most_common()]
        for group, counter in counters.items()
    }


def run(book_id):
    path = cache_path(book_id, "entities")

    cached = load_json(path)
    if cached is not None:
        return cached

    result = find_entities(get_text(book_id))
    save_json(path, result)
    return result
