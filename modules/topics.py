import re
from math import ceil
from sklearn.decomposition import NMF
from modules.cache import load_json, save_json
from modules.nlp import lemmatize, vectorize
from utils.path_config import cache_path, get_text

TOPIC_POS = {"NOUN", "PROPN", "ADJ"}
TOPIC_COUNT = 4            # combien de themes on veut trouver
WORDS_PER_TOPIC = 10     # combien de mots on garde pour decrire chaque theme
MAX_DF = 0.8         # word frequency in the document

EXPLICIT_HEADING = re.compile(
    r"^\s*(CHAPTER|PART|SECTION)\s+([IVXLCDM]+|\d+)\.?\b.*$",
    re.IGNORECASE,
)
ROMAN_HEADING = re.compile(r"^\s*[IVXLCDM]+\.\s*$")


def split_equal_sections(text):
    words = text.split()
    if not words:
        return []

    section_size = ceil(len(words) / TOPIC_COUNT)
    sections = []
    for start in range(0, len(words), section_size):
        section = " ".join(words[start:start + section_size])
        sections.append(section)
    return sections


def split_from_headings(text, pattern):
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if pattern.match(line)]
    starts = [
        start for position, start in enumerate(starts)
        if not (
            (position > 0 and start == starts[position - 1] + 1)
            or (position + 1 < len(starts) and starts[position + 1] == start + 1)
        )
    ]
    if len(starts) < TOPIC_COUNT:
        return []

    sections = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        section = "\n".join(lines[start + 1:end]).strip()
        if section:
            sections.append(section)
    return sections


def split_sections(text):
    for pattern in (EXPLICIT_HEADING, ROMAN_HEADING):
        sections = split_from_headings(text, pattern)
        if len(sections) >= TOPIC_COUNT:
            return sections
    return split_equal_sections(text)


def strongest_words(weights, words):
    # argsort() trie les positions du plus PETIT au plus grand poids ;
    # [::-1] inverse la liste pour avoir le plus GRAND en premier.
    sorted_positions = weights.argsort()[::-1]

    result = []
    for position in sorted_positions[:WORDS_PER_TOPIC]:
        if weights[position] <= 0:
            continue  # un poids nul ne represente pas le theme
        result.append(words[position])
    return result


def empty_result():
    return {number: [] for number in range(1, TOPIC_COUNT + 1)}


def find_topics(text):
    sections = [lemmatize(section, keep_pos=TOPIC_POS) for section in split_sections(text)]
    if not sections:
        return empty_result()

    # 1) Transformer le texte en chiffres (TF-IDF).
    #    Chaque tranche devient une ligne de nombres ; un mot a un score eleve
    #    s'il est frequent dans cette tranche mais rare dans les autres.
    vectorizer = vectorize(
        stop_words="english",
        max_df=MAX_DF,
    )
    matrix = vectorizer.fit_transform(sections)
    words = vectorizer.get_feature_names_out()

    # 2) NMF : regrouper les mots qui apparaissent souvent ensemble en themes.
    #    On ne peut pas demander plus de themes que de tranches ou de mots.
    topic_count = min(TOPIC_COUNT, matrix.shape[0], matrix.shape[1])
    model = NMF(
        n_components=topic_count,
        init="nndsvda",
        random_state=42,   # resultat toujours identique (stable et reproductible)
        max_iter=600,
    )
    model.fit_transform(matrix)

    # 3) Pour chaque theme, ses mots les plus representatifs.
    topics = {}
    for number, topic_weights in enumerate(model.components_):
        topic_words = strongest_words(topic_weights, words)
        topics[number + 1] = topic_words
    for number in range(1, TOPIC_COUNT + 1):
        topics.setdefault(number, [])
    return topics


def run(book_id):
    """Point d'entree : renvoie les themes du livre (depuis le cache si possible)."""
    path = cache_path(book_id, "topics")

    cached = load_json(path)
    if cached is not None:
        return cached

    text = get_text(book_id)
    result = find_topics(text)
    save_json(path, result)
    return result
