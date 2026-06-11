import requests

URLS = [
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",
    "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt",
]

HEADERS = {"User-Agent": "bookworm/0.1"}


def download(book_id):
    for url_template in URLS:
        url = url_template.format(id=book_id)
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.ok:
            response.encoding = "utf-8"
            return response.text

    raise RuntimeError(f"Livre {book_id} introuvable sur Project Gutenberg")
