"""Metadonnees d'un livre (titre, auteur, bookshelves) via le RDF Gutenberg.

Le texte brut ne contient pas de metadonnees fiables (et les bookshelves n'y
sont pas du tout). On les lit donc dans le fichier RDF officiel :
    https://www.gutenberg.org/ebooks/<id>.rdf
Resultat mis en cache pour ne pas refaire l'appel reseau.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from modules.cache import load_json, save_json
from utils.path_config import cache_path

RDF_URL = "https://www.gutenberg.org/ebooks/{id}.rdf"
HEADERS = {"User-Agent": "bookworm/0.1"}

NS = {
    "dcterms": "http://purl.org/dc/terms/",
    "pgterms": "http://www.gutenberg.org/2009/pgterms/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


def _fetch_rdf(book_id: int) -> str:
    response = requests.get(RDF_URL.format(id=book_id), headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def _flip_name(name: str) -> str:
    # Gutenberg ecrit "Stoker, Bram" -> on remet "Bram Stoker".
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def _parse(xml_text: str, book_id: int) -> dict:
    root = ET.fromstring(xml_text)

    title_el = root.find(".//dcterms:title", NS)
    title = title_el.text.strip() if title_el is not None and title_el.text else "Unknown title"

    name_el = root.find(".//dcterms:creator/pgterms:agent/pgterms:name", NS)
    author = _flip_name(name_el.text.strip()) if name_el is not None and name_el.text else "Unknown author"

    bookshelves = [
        value.text.strip()
        for value in root.findall(".//pgterms:bookshelf/rdf:Description/rdf:value", NS)
        if value.text
    ]

    return {
        "id": str(book_id),
        "title": title,
        "authors": author,
        "bookshelves": ", ".join(bookshelves),
    }


def run(book_id: int) -> dict:
    path = cache_path(book_id, "metadata")

    cached = load_json(path)
    if cached is not None and "title" in cached:
        return cached

    data = _parse(_fetch_rdf(book_id), book_id)
    save_json(path, data)
    return data
