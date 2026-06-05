from __future__ import annotations

from collections import Counter

from modules.cache import load_json, save_json
from modules.nlp import load_spacy, spacy_chunks
from utils.path_config import cache_path, get_text

CONTEXT_WINDOW = 4
ACTION_POS = {"VERB", "AUX"}
CHARACTER_DEPS = {"nsubj", "dobj", "pobj", "attr", "appos", "conj"}
INVALID_ENTITY_STARTS = {"a", "an", "the", "this", "that", "these", "those"}
INVALID_ENTITY_POS = {"ADV", "VERB"}
CHARACTER_LABELS = {"PERSON", "GPE", "LOC", "FAC"}
MIN_CHARACTER_CONTEXTS = 2
LOCATION_PREPOSITIONS = {
    "across",
    "behind",
    "beside",
    "between",
    "from",
    "in",
    "inside",
    "into",
    "near",
    "of",
    "on",
    "onto",
    "outside",
    "through",
    "to",
    "toward",
    "towards",
    "under",
    "upon",
}
LOCATION_NOUN_PREPOSITIONS = LOCATION_PREPOSITIONS - {"of", "on", "upon"}
POSSESSIVE_MARKERS = {"'s", "’s"}
OWNER_POS = {"PROPN", "NOUN", "ADJ"}
LOCATION_PHRASE_POS = {"PROPN", "NOUN", "ADJ"}
NOUN_POS = {"NOUN", "PROPN"}
NON_LOCATION_NOUNS = {
    "amusement",
    "arm",
    "attention",
    "chance",
    "chair",
    "crown",
    "cry",
    "dinner",
    "disgust",
    "dream",
    "ear",
    "eagle",
    "elbow",
    "eye",
    "feeling",
    "foot",
    "favour",
    "glove",
    "grasp",
    "hair",
    "hand",
    "handwriting",
    "head",
    "knee",
    "lap",
    "life",
    "love",
    "master",
    "memory",
    "mouth",
    "nature",
    "neck",
    "nostril",
    "party",
    "place",
    "province",
    "remark",
    "shawl",
    "shoulder",
    "slate",
    "speech",
    "surprise",
    "tail",
    "tone",
    "voice",
}


def normalize_entity(name: str) -> str:
    return " ".join(name.split()).strip(".,;:!?\"'“”‘’")


def valid_entity_name(name: str) -> bool:
    upper = name.upper()
    return (
        name
        and "'s" not in name
        and "’s" not in name
        and not upper.startswith("CHAPTER")
        and not upper.startswith("PART")
        and not upper.startswith("SECTION")
    )


def is_lowercase_phrase(entity) -> bool:
    return not any(token.text[:1].isupper() for token in entity if token.is_alpha)


def valid_character_entity(entity) -> bool:
    name = normalize_entity(entity.text)
    return (
        valid_entity_name(name)
        and entity[0].lower_ not in INVALID_ENTITY_STARTS
        and not any(token.pos_ in INVALID_ENTITY_POS for token in entity)
        and not is_lowercase_phrase(entity)
    )


def valid_location_entity(entity) -> bool:
    name = normalize_entity(entity.text)
    previous = entity.doc[entity.start - 1] if entity.start > 0 else None
    return (
        valid_entity_name(name)
        and not is_lowercase_phrase(entity)
        and not (previous is not None and previous.like_num)
        and not (noun_lemmas(entity) & NON_LOCATION_NOUNS)
    )


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
        return int(has_location_context(entity))
    return 0


def has_character_context(entity) -> bool:
    return entity.root.dep_ in CHARACTER_DEPS and entity.root.head.pos_ == "VERB"


def has_location_context(entity) -> bool:
    return any(
        token.pos_ == "ADP" and token.lower_ in LOCATION_PREPOSITIONS
        for token in context_tokens(entity)
    )


def has_leading_location_context(doc, start: int) -> bool:
    for index in range(start - 1, max(-1, start - CONTEXT_WINDOW - 1), -1):
        token = doc[index]
        if token.pos_ == "DET" or token.is_punct:
            continue
        return token.pos_ == "ADP" and token.lower_ in LOCATION_NOUN_PREPOSITIONS
    return False


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


def noun_lemmas(tokens, pos=NOUN_POS) -> set[str]:
    return {
        token.lemma_.lower()
        for token in tokens
        if token.is_alpha and not token.is_stop and token.pos_ in pos
    }


def is_location_phrase(tokens, location_nouns: set[str]) -> bool:
    return bool(noun_lemmas(tokens, {"NOUN"}) & location_nouns)


def entity_group(entity, character_names: set[str], location_nouns: set[str]):
    name = normalize_entity(entity.text)
    if entity.label_ in CHARACTER_LABELS and valid_character_entity(entity) and name in character_names:
        return "characters"
    if entity.label_ == "GPE" and valid_location_entity(entity) and has_location_context(entity):
        return "locations"
    if (
        entity.label_ in {"LOC", "FAC"}
        and valid_location_entity(entity)
        and is_location_phrase(entity, location_nouns)
    ):
        return "locations"
    return None


def possessive_locations(doc, location_nouns: set[str]):
    for token in doc:
        if token.text not in POSSESSIVE_MARKERS:
            continue

        owner = owner_tokens(doc, token.i)
        location = location_tokens(doc, token.i)
        if not owner or not location or not is_location_phrase(location, location_nouns):
            continue

        phrase = clean_phrase(owner + [token] + location)
        if phrase:
            yield phrase


def learn_book_entities(docs) -> tuple[set[str], set[str]]:
    character_contexts = Counter()
    location_nouns = Counter()

    for doc in docs:
        for entity in doc.ents:
            name = normalize_entity(entity.text)
            if (
                entity.label_ in CHARACTER_LABELS
                and valid_character_entity(entity)
                and has_character_context(entity)
            ):
                character_contexts[name] += 1

        for token in doc:
            if token.text not in POSSESSIVE_MARKERS:
                continue
            owner = owner_tokens(doc, token.i)
            location = location_tokens(doc, token.i)
            if owner and location and has_leading_location_context(doc, owner[0].i):
                location_nouns.update(
                    noun_lemmas(location, {"NOUN"}) - NON_LOCATION_NOUNS
                )

    character_names = {
        name for name, count in character_contexts.items()
        if count >= MIN_CHARACTER_CONTEXTS
    }
    return character_names, set(location_nouns)


def find_entities(text: str) -> dict[str, list[str]]:
    nlp = load_spacy()
    docs = list(nlp.pipe(spacy_chunks(text)))
    character_names, location_nouns = learn_book_entities(docs)
    counters = {
        "characters": Counter(),
        "locations": Counter(),
    }

    for doc in docs:
        for entity in doc.ents:
            group = entity_group(entity, character_names, location_nouns)
            if group is None:
                continue
            name = normalize_entity(entity.text)
            if valid_entity_name(name):
                counters[group][name] += 1 + context_bonus(entity, group)
        for location in possessive_locations(doc, location_nouns):
            counters["locations"][location] += 2

    characters = [name for name, _ in counters["characters"].most_common()]
    character_names = set(characters)
    locations = [
        name for name, _ in counters["locations"].most_common()
        if name not in character_names
    ]

    return {
        "characters": characters,
        "locations": locations,
    }


def run(book_id):
    path = cache_path(book_id, "entities")

    cached = load_json(path)
    if cached is not None:
        return cached

    result = find_entities(get_text(book_id))
    save_json(path, result)
    return result
