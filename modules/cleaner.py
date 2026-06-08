from __future__ import annotations

import re

START_MARKER = "*** START OF "
END_MARKER = "*** END OF "
ILLUSTRATION_MARKER = "[Illustration]"

# Un titre de chapitre : CHAPTER/LETTER/PART suivi d'un numero (romain ou chiffre).
# On exige le numero pour ne pas confondre avec le mot courant "part of the..."
_HEADING = re.compile(r"^\s*(chapter|letter|part)\s+([ivxlcdm]+|\d+)\b", re.IGNORECASE)


def skip_front_matter(text: str) -> str:
    """Coupe la table des matieres / preface : commence au 1er vrai chapitre.

    Le titre du 1er chapitre (ex. "CHAPTER I") apparait deux fois : une fois
    dans la table des matieres, une fois comme vrai titre. On saute donc a sa
    2e occurrence. S'il n'apparait qu'une fois (pas de table des matieres),
    on saute a cette occurrence (= le vrai chapitre 1).
    """
    lines = text.splitlines()
    headings = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match:
            signature = (match.group(1).lower(), match.group(2).lower())
            headings.append((index, signature))

    if not headings:
        return text  # pas de titre detecte : on ne touche a rien

    first_signature = headings[0][1]
    occurrences = [index for index, signature in headings if signature == first_signature]
    start = occurrences[1] if len(occurrences) >= 2 else occurrences[0]
    return "\n".join(lines[start:]).strip()


def clean(text: str) -> str:
    start = text.find(START_MARKER)
    if start != -1:
        line_end = text.find("\n", start)
        text = text[line_end + 1:]
        illustration = text.find(ILLUSTRATION_MARKER)
        if illustration != -1:
            text = text[illustration + len(ILLUSTRATION_MARKER):]

    end = text.find(END_MARKER)
    if end != -1:
        text = text[:end]

    return skip_front_matter(text.strip())
