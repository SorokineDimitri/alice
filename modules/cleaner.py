

from __future__ import annotations

START_MARKER = "*** START OF "
END_MARKER = "*** END OF "
ILLUSTRATION_MARKER = "[Illustration]"


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

    return text.strip()