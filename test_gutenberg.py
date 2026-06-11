"""Tests manuels du module gutenberg.

Lance avec: .venv/bin/python3 test_gutenberg.py
"""

from modules.gutenberg import download


print("Test 1 — Livre qui existe (Alice, id=11)")
text = download(11)
assert len(text) > 1000, "Le texte est trop court"
assert "Alice" in text, "Le mot 'Alice' devrait etre dans le texte"
print(f"  OK ({len(text)} caracteres)")


print("Test 2 — Autre livre (Frankenstein, id=84)")
text = download(84)
assert len(text) > 1000
assert "Frankenstein" in text
print(f"  OK ({len(text)} caracteres)")


print("Test 3 — Livre inexistant (id=999999999)")
try:
    download(999999999)
    print("  ECHEC : aurait du lever une erreur")
except RuntimeError as exc:
    print(f"  OK (erreur attrapee : {exc})")


print("\nTous les tests sont passes.")
