from __future__ import annotations

import functools
import json
from collections import Counter
from pathlib import Path

from modules.cache import load_json, save_json
from modules.nlp import load_spacy, spacy_chunks
from utils import metadata
from utils.path_config import cache_path, get_raw_text, get_text

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "entity_rules.json"
CONTEXT_WINDOW = 4
ENTITY_LIMIT = 20
ENTITY_SAMPLE_CHARS = 250_000
LARGE_BOOK_CHARS = ENTITY_SAMPLE_CHARS * 3
ACTION_POS = {"VERB", "AUX"}
CHARACTER_DEPS = {"nsubj", "dobj", "pobj", "attr", "appos", "conj"}
INVALID_ENTITY_STARTS = {"a", "an", "the", "this", "that", "these", "those"}
INVALID_ENTITY_POS = {"ADV", "VERB"}
CHARACTER_LABELS = {"PERSON"}
LOCATION_LABELS = {"GPE", "LOC", "FAC"}
MIN_CHARACTER_CONTEXTS = 2
LOCATION_NOUN_EXCLUDED_PREPOSITIONS = {"of", "on", "upon"}
WEAK_LOCATION_PREPOSITIONS = {"of", "to", "toward", "towards"}
POSSESSIVE_MARKERS = {"'s", "’s"}
OWNER_POS = {"PROPN", "NOUN", "ADJ"}
LOCATION_PHRASE_POS = {"PROPN", "NOUN", "ADJ"}
NOUN_POS = {"NOUN", "PROPN"}
@functools.lru_cache(maxsize=1)
def entity_rules() -> dict[str, set[str]]:
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return {
        key: {
            value.lower()
            for value in values
            if isinstance(value, str)
        }
        for key, values in payload.items()
        if isinstance(values, list)
    }


def location_prepositions() -> set[str]:
    return entity_rules().get("location_prepositions", set())


def location_noun_prepositions() -> set[str]:
    return location_prepositions() - LOCATION_NOUN_EXCLUDED_PREPOSITIONS


def strong_location_prepositions() -> set[str]:
    return location_prepositions() - WEAK_LOCATION_PREPOSITIONS


def non_location_nouns() -> set[str]:
    return entity_rules().get("non_location_nouns", set())


def generic_location_nouns() -> set[str]:
    return entity_rules().get("location_nouns", set())


def normalize_entity(name: str) -> str:
    return " ".join(name.split()).strip(".,;:!?\"'“”‘’")


def comparable_name(name: str) -> str:
    return " ".join(
        token.lower()
        for token in re_words(name)
    )


def title_character_match(title: str, character: str) -> bool:
    title_key = comparable_name(title)
    character_key = comparable_name(character)
    return (
        bool(title_key and character_key)
        and (
            character_key == title_key
            or (
                len(character_key.split()) >= 2
                and character_key in title_key
            )
        )
    )


def re_words(name: str) -> list[str]:
    return [
        word
        for word in name.replace("’", "'").replace("-", " ").split()
        if any(char.isalpha() for char in word)
    ]


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
        and not (noun_lemmas(entity) & non_location_nouns())
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
        token.pos_ == "ADP" and token.lower_ in location_prepositions()
        for token in context_tokens(entity)
    )


def has_strong_location_context(entity) -> bool:
    return any(
        token.pos_ == "ADP" and token.lower_ in strong_location_prepositions()
        for token in context_tokens(entity)
    )


def has_leading_location_context(doc, start: int) -> bool:
    for index in range(start - 1, max(-1, start - CONTEXT_WINDOW - 1), -1):
        token = doc[index]
        if token.pos_ == "DET" or token.is_punct:
            continue
        return token.pos_ == "ADP" and token.lower_ in location_noun_prepositions()
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


def is_possessive_location_phrase(tokens) -> bool:
    return bool(noun_lemmas(tokens, {"NOUN"}) & generic_location_nouns())


def is_character_entity(entity, character_names: set[str]) -> bool:
    name = normalize_entity(entity.text)
    return (
        entity.label_ in CHARACTER_LABELS
        and valid_character_entity(entity)
        and name in character_names
    )


def is_location_entity(entity, location_nouns: set[str]) -> bool:
    if entity.label_ == "GPE":
        return valid_location_entity(entity) and has_strong_location_context(entity)
    return (
        entity.label_ in {"LOC", "FAC"}
        and valid_location_entity(entity)
        and is_location_phrase(entity, location_nouns)
    )


def entity_group(entity, character_names: set[str], location_nouns: set[str]):
    if is_character_entity(entity, character_names):
        return "characters"
    if is_location_entity(entity, location_nouns):
        return "locations"
    return None


def possessive_locations(doc, location_nouns: set[str]):
    for token in doc:
        if token.text not in POSSESSIVE_MARKERS:
            continue

        owner = owner_tokens(doc, token.i)
        location = location_tokens(doc, token.i)
        if (
            not owner
            or not location
            or not is_location_phrase(location, location_nouns)
            or not is_possessive_location_phrase(location)
        ):
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
                    (noun_lemmas(location, {"NOUN"}) & generic_location_nouns())
                    - non_location_nouns()
                )

    character_names = {
        name for name, count in character_contexts.items()
        if count >= MIN_CHARACTER_CONTEXTS
    }
    return character_names, set(location_nouns)


def person_entity_scores(docs) -> Counter:
    scores = Counter()

    for doc in docs:
        for entity in doc.ents:
            if not valid_character_entity(entity):
                continue
            name = normalize_entity(entity.text)
            if entity.label_ == "PERSON":
                scores[name] += 2
            elif has_character_context(entity):
                scores[name] += 1

    return scores


def entity_text_sample(text: str) -> str:
    if len(text) <= LARGE_BOOK_CHARS:
        return text

    middle_start = (len(text) - ENTITY_SAMPLE_CHARS) // 2
    return "\n\n".join(
        (
            text[:ENTITY_SAMPLE_CHARS],
            text[middle_start:middle_start + ENTITY_SAMPLE_CHARS],
            text[-ENTITY_SAMPLE_CHARS:],
        )
    )


def promote_title_character(book_id: int, characters: list[str]) -> list[str]:
    title = metadata.find_title(get_raw_text(book_id))
    if not title:
        return characters

    for index, character in enumerate(characters):
        if title_character_match(title, character):
            return [character] + characters[:index] + characters[index + 1:]
    return characters


def find_entities(text: str, book_id: int | None = None) -> dict[str, list[str]]:
    nlp = load_spacy()
    docs = list(nlp.pipe(spacy_chunks(entity_text_sample(text))))
    character_names, location_nouns = learn_book_entities(docs)
    person_scores = person_entity_scores(docs)
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
            counters[group][name] += 1 + context_bonus(entity, group)
        for location in possessive_locations(doc, location_nouns):
            counters["locations"][location] += 2

    ranked_characters = [
        name for name, _ in counters["characters"].most_common()
    ]
    character_names = set(ranked_characters)
    characters = ranked_characters[:ENTITY_LIMIT]
    if book_id is not None:
        characters = promote_title_character(book_id, characters)
    locations = [
        name for name, _ in counters["locations"].most_common()
        if name not in character_names
        and person_scores[name] < counters["locations"][name]
    ][:ENTITY_LIMIT]

    return {
        "characters": characters,
        "locations": locations,
    }


def valid_cached_entities(payload) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("characters"), list)
        and isinstance(payload.get("locations"), list)
        and len(payload["characters"]) <= ENTITY_LIMIT
        and len(payload["locations"]) <= ENTITY_LIMIT
        and all(isinstance(name, str) for name in payload["characters"])
        and all(isinstance(name, str) for name in payload["locations"])
    )


def run(book_id, force: bool = False):
    path = cache_path(book_id, "entities")

    cached = load_json(path)
    if not force and cached is not None and valid_cached_entities(cached):
        return cached

    result = find_entities(get_text(book_id), book_id)
    save_json(path, result)
    return result
