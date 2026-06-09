# Référence des modules

Ce document décrit chaque module du projet : son rôle, son API, son algorithme et ses entrées/sorties. Pour la vue d'ensemble (pipeline, communication entre fichiers, cache), voir [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Sommaire

**Interface** · [bookworm.py](#bookwormpy--interface-en-ligne-de-commande)
**Acquisition** · [gutenberg.py](#modulesgutenbergpy--téléchargement) · [cleaner.py](#modulescleanerpy--nettoyage-du-texte) · [path_config.py](#utilspath_configpy--accès-aux-textes)
**Outils** · [nlp.py](#modulesnlppy--boîte-à-outils-nlp) · [cache.py](#modulescachepy--persistance-json)
**Analyse** · [lexdiv.py](#moduleslexdivpy--diversité-lexicale) · [topics.py](#modulestopicspy--extraction-de-thèmes) · [entities.py](#modulesentitiespy--personnages-et-lieux) · [similarity.py](#modulessimilaritypy--livres-similaires)
**Synthèse** · [metadata.py](#utilsmetadatapy--métadonnées-du-livre) · [overview.py](#modulesoverviewpy--génération-par-gabarit) · [summary.py](#modulessummarypy--résumé) · [card.py](#modulescardpy--book-card)

---

## `bookworm.py` — interface en ligne de commande

**Rôle.** Point d'entrée unique. Parse les arguments, dispatche vers le bon module, formate la sortie.

**Fonctionnement.**
- Six options mutuellement exclusives (`--lexdiv`, `--topics`, `--entities`, `--summarize`, `--similar`, `--card`), chacune prenant un ID Gutenberg.
- La table `TASK_MODULES` associe chaque option au nom de son module ; `run_task()` importe le module **dynamiquement** (`__import__`) et appelle son `run(book_id)`. Seul le module demandé est chargé en mémoire.
- Formatage : une chaîne est imprimée brute (pour rendre les sauts de ligne du résumé), tout le reste en JSON indenté (`ensure_ascii=False` pour préserver les accents).
- Gestion d'erreur : toute `RuntimeError` (livre introuvable, tâche non implémentée) est imprimée sur `stderr` avec un code de sortie `1`.

---

## `modules/gutenberg.py` — téléchargement

**Rôle.** Obtenir le texte brut d'un livre à partir de son ID.

**API.** `download(book_id: int) -> str`

**Fonctionnement.** Les livres de Gutenberg sont hébergés sous deux schémas d'URL selon leur âge ; le module essaie les deux dans l'ordre :
1. `https://www.gutenberg.org/files/{id}/{id}-0.txt`
2. `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt`

Le premier qui répond `200` gagne. L'encodage est forcé en UTF-8 (les en-têtes HTTP de Gutenberg sont parfois faux). Si aucune URL ne répond, `RuntimeError` est levée — c'est elle qui remonte jusqu'au CLI.

**Tests.** `test_gutenberg.py` couvre : livre existant, livre servi par le second miroir, livre inexistant.

---

## `modules/cleaner.py` — nettoyage du texte

**Rôle.** Transformer un fichier Gutenberg brut en texte littéraire pur.

**API.** `clean(text: str) -> str`

**Fonctionnement.** Deux passes :

1. **Bornes Gutenberg** — tout fichier Gutenberg encadre l'œuvre par `*** START OF THE PROJECT GUTENBERG EBOOK ... ***` et `*** END OF ... ***`. Le texte est découpé entre ces deux marqueurs ; un éventuel crédit `[Illustration]` qui suit le START est également sauté.

2. **Table des matières** (`skip_front_matter`) — l'astuce centrale : le titre du premier chapitre (ex. `CHAPTER I`) apparaît **deux fois** dans la plupart des livres — une fois dans la table des matières, une fois comme vrai titre. Le nettoyeur indexe tous les titres (`CHAPTER|LETTER|PART` + numéro romain ou arabe), puis saute à la **deuxième occurrence** de la signature du premier titre. S'il n'y a qu'une occurrence (pas de table des matières), il saute à celle-ci. S'il n'y a aucun titre, le texte est laissé intact.

**Pourquoi exiger un numéro après `CHAPTER/PART` ?** Pour ne pas confondre un titre avec le mot courant *« part of the… »* en début de ligne.

---

## `utils/path_config.py` — accès aux textes

**Rôle.** Centraliser les chemins et fournir les deux primitives d'accès au texte utilisées par tout le projet.

**API.**

| Fonction | Retour |
|---|---|
| `raw_path(book_id)` | `data/raw/<id>.txt` |
| `cache_path(book_id, task)` | `data/cache/<id>_<task>.json` |
| `get_raw_text(book_id)` | Texte brut — lu sur disque, ou téléchargé puis écrit sur disque |
| `get_text(book_id)` | Texte **nettoyé** : `clean(get_raw_text(id))` |

**Convention.** Les modules d'analyse appellent `get_text()` (texte littéraire) ; `metadata.py` appelle `get_raw_text()` car le titre et l'auteur se trouvent justement dans l'en-tête que `clean()` supprime.

---

## `modules/nlp.py` — boîte à outils NLP

**Rôle.** Le seul module qui parle à spaCy et à scikit-learn. Tous les réglages NLP partagés vivent ici.

**API.**

| Fonction | Rôle |
|---|---|
| `vectorize(stop_words, max_df)` | Fabrique un `TfidfVectorizer` configuré de manière homogène pour tout le projet : minuscules, accents retirés, tokens alphabétiques de 2+ lettres (apostrophes acceptées : *don't*), normalisation L2, lissage IDF |
| `load_spacy(disable)` | Charge `en_core_web_sm`, **mémoïsé** par `functools.lru_cache` — le modèle (~1 s de chargement) n'est chargé qu'une fois par configuration de pipeline |
| `spacy_chunks(text)` | Découpe le texte en blocs de 1 000 000 caractères, la limite par appel de spaCy — indispensable pour les très longs romans |
| `lemmatize(text, keep_pos)` | Réduit le texte à ses **lemmes porteurs de sens** : ne garde que les parts du discours demandées (noms, adjectifs, verbes…), élimine stop words, ponctuation et non-alphabétiques. spaCy gère contractions (*don't* → *do/not*) et flexions (*came* → *come*) |

**Optimisation notable.** `lemmatize` charge spaCy avec `disable=("parser", "ner")` : le tagger et le lemmatiseur suffisent, le pipeline est nettement plus rapide.

---

## `modules/cache.py` — persistance JSON

**Rôle.** Lecture/écriture JSON défensive, partagée par tous les modules.

**API.**

- `load_json(path, required_keys=None)` — retourne le dictionnaire, ou `None` si : fichier absent, JSON invalide, contenu non-dictionnaire, ou clés requises manquantes. **Ne lève jamais** : un cache cassé équivaut à un cache absent.
- `save_json(path, payload)` — crée les dossiers parents si besoin, écrit en UTF-8 indenté.

---

## `modules/lexdiv.py` — diversité lexicale

**Rôle.** Mesurer la richesse du vocabulaire d'un livre.

**API.** `run(book_id) -> dict` — cache : `data/cache/<id>_lexdiv.json`

**Algorithme.** Le texte nettoyé est tokenisé avec le même analyseur que le TF-IDF du projet (cohérence des comptages), puis un simple `Counter` produit :

| Clé | Nom complet | Formule | Interprétation |
|---|---|---|---|
| `tok` | tokens | nombre total de mots | longueur du livre |
| `typ` | types | nombre de mots **uniques** | étendue du vocabulaire |
| `hap` | hapax legomena | mots utilisés **une seule fois** | inventivité lexicale |
| `ttr` | type-token ratio | `typ / tok` | richesse relative (↑ = plus varié) |
| `mwl` | mean word length | moyenne des longueurs | complexité des mots |
| `mwf` | mean word frequency | `tok / typ` | répétitivité (↑ = plus répétitif) |

**Exemple** (*Alice*, ID 11) : 25 412 tokens, 2 548 types, 1 104 hapax, TTR ≈ 0,10.

---

## `modules/topics.py` — extraction de thèmes

**Rôle.** Déterminer le thème dominant de chaque chapitre, avec ses mots représentatifs.

**API.** `run(book_id) -> dict[str, list[str]]` — clés `"<n°>: <thème>"`, valeurs = 10 mots. Cache : `<id>_topics.json`. Expose aussi `topic_themes(book_id)` (la liste ordonnée des thèmes, consommée par `metadata.py`).

**Algorithme**, en quatre temps :

1. **Sectionnement** (`author_sections`) — découpage prioritaire sur les titres de l'auteur (`CHAPTER X`, `PART IV`, ou lignes en chiffres romains seuls type `VII.`). Repli : blocs de 1 500 lemmes. Les sections < 80 mots sont écartées.
2. **Lemmatisation** — chaque section est réduite à ses noms, noms propres, adjectifs et verbes (`THEME_POS`), via `nlp.lemmatize`.
3. **TF-IDF inter-sections** — `max_df=0.3` : un mot présent dans plus de 30 % des chapitres est ignoré, ce qui élimine les mots du *livre* (les noms des héros, le vocabulaire récurrent) pour ne garder que ce qui rend **chaque chapitre distinctif**.
4. **Projection sur le dictionnaire** (`best_theme`) — pour chacun des 147 thèmes de `literary_themes.json`, on somme les poids TF-IDF des mots de la section qui appartiennent au thème ; le meilleur score gagne (`general` si aucun mot ne matche). Les 10 mots retenus privilégient ceux du thème gagnant, complétés par les plus saillants.

**Sortie** = l'**arc narratif** du livre. Exemple (*Alice*) : `1: nature`, `2: nature`, `3: quest`, … `12: madness` — d'où la phrase du résumé *« the story moves from nature toward madness »*.

---

## `modules/entities.py` — personnages et lieux

**Rôle.** Extraire les personnages et lieux principaux. Le module le plus sophistiqué du projet (415 lignes) : la NER brute de spaCy est trop bruitée sur la littérature classique, elle est donc encadrée par des règles.

**API.** `run(book_id) -> {"characters": [...], "locations": [...]}` (max 20 chacun, triés par importance). Cache : `<id>_entities.json`.

**Algorithme**, en cinq temps sur un même passage spaCy :

1. **Échantillonnage** (`entity_text_sample`) — au-delà de 750 000 caractères, seuls le début, le milieu et la fin (3 × 250 000) sont analysés : les protagonistes y apparaissent forcément, et le coût NER reste borné.

2. **Apprentissage propre au livre** (`learn_book_entities`) — première passe qui apprend deux ensembles :
   - *les personnages du livre* : entités `PERSON` vues **au moins 2 fois en position d'acteur** (sujet/objet d'un verbe, via les dépendances syntaxiques). C'est ce qui permet d'accepter « Mouse » ou « Hatter » comme personnages dans *Alice* sans polluer un roman réaliste ;
   - *les noms de lieux actifs dans ce livre* : noms génériques (`garden`, `house`…) effectivement employés après une préposition locative.

3. **Filtres de validité** — rejet des entités commençant par un déterminant, contenant un possessif, entièrement en minuscules, commençant par `CHAPTER/PART`, précédées d'un nombre, ou contenant un nom de la liste noire `non_location_nouns` (`voice`, `heart`…).

4. **Comptage pondéré** — chaque occurrence valide vaut 1 point, **+1 de bonus contextuel** (verbe d'action à proximité pour un personnage ; préposition locative pour un lieu). Les lieux possessifs (*« the Queen's garden »*) sont reconstruits token par token et valent 2 points. Les `GPE` (villes, pays) exigent une préposition locative **forte** (`in`, `at`, `near`… mais pas `of`) pour éviter les mentions rhétoriques.

5. **Arbitrages finaux** — un nom classé à la fois personnage et lieu est tranché par comparaison des scores (un nom plus souvent vu comme personne que comme lieu est écarté des lieux) ; le personnage présent dans le **titre du livre** (via `metadata.find_title`) est promu en tête de liste.

**Configuration externalisée** : prépositions et listes de noms vivent dans `data/entity_rules.json` — ajustables sans toucher au code.

---

## `modules/similarity.py` — livres similaires

**Rôle.** Recommander les 5 livres les plus proches parmi un catalogue de 21 classiques (3 catégories : jeunesse, policier/mystère, SF/fantasy).

**API.** `prepare(book_id)` (télécharge le corpus) puis `run(book_id) -> list[str]` (5 titres, ordre décroissant). Cache : `<id>_similar.json`.

**Algorithme.**

1. **Constitution du corpus** (`prepare`) — les textes manquants du catalogue sont téléchargés en **concurrence** avec `asyncio` (sémaphore à 4 téléchargements simultanés ; `requests` étant bloquant, chaque appel passe par `asyncio.to_thread`). Un livre indisponible est simplement écarté du corpus.
2. **Vectorisation** — tous les textes (catalogue + livre cible) sont vectorisés en TF-IDF dans la **même matrice** : les poids IDF sont calculés sur le corpus entier, ce qui neutralise le vocabulaire commun à tous les classiques.
3. **Score** — `cosinus(cible, candidat)` + **bonus de +0,15** si les deux livres partagent la même catégorie éditoriale. Le bonus encode une connaissance métier que le lexique seul capte mal : deux romans jeunesse se ressemblent plus que leur seul vocabulaire ne le suggère.
4. **Classement** — tri décroissant, top 5, conversion des IDs en titres via le catalogue.

---

## `utils/metadata.py` — métadonnées du livre

**Rôle.** Extraire `id`, `title`, `authors` et `bookshelves` **sans aucun appel réseau supplémentaire** : tout est lu dans l'en-tête du fichier déjà téléchargé.

**API.** `info(book_id) -> dict[str, str]`

**Fonctionnement.**
- `useful_lines` isole l'en-tête : les lignes entre le marqueur `*** START OF` et le premier signe de contenu (`CONTENTS`, `CHAPTER`, `DRAMATIS PERSONAE`…).
- `find_author` cherche une ligne `by …` / `Author: …` (en ignorant le piège *« By the same author »*) ; si le marqueur est seul sur sa ligne, l'auteur est sur la ligne adjacente.
- `find_title` concatène les lignes qui précèdent l'auteur (en sautant `[Illustration]`).
- `bookshelves` n'est **pas** extrait du fichier : c'est la liste des thèmes les plus fréquents du livre, fournie par `topics.topic_themes()` — un exemple de composition entre couches.

---

## `modules/overview.py` — génération par gabarit

**Rôle.** Produire la phrase d'accroche du livre par **template NLG** : des phrases à trous remplies avec les résultats des autres modules. Aucun modèle ne tourne.

**API.** `build(book_id) -> str` (et `run` pour le CLI).

**Fonctionnement.** Trois phrases assemblées puis jointes :

| Phrase | Construction | Sources |
|---|---|---|
| **Ouverture** | *« {titre}, by {auteur}, follows {héros}, the main character, alongside figures such as {3 secondaires}, in {lieu} … »* — avec dégradations propres si pas de personnages ou pas de lieu | `metadata`, `entities` |
| **Thèmes** | *« {titre} presents a narrative that gradually unfolds around {4 thèmes} »* | `topics` |
| **Arc narratif** | *« Across its {n} chapters, the story moves from {thème du 1ᵉʳ chapitre} toward {thème du dernier} »* — ou *« centers on … »* si le thème ne change pas | `topics` (ordre des sections) |

Le **lieu principal** est choisi intelligemment : un lieu qui apparaît dans le titre du livre (ex. *Wonderland*) est préféré au lieu le plus fréquent. Les listes sont jointes à l'anglaise (*« a, b and c »*).

---

## `modules/summary.py` — résumé

**Rôle.** Fine couche d'orchestration : ajoute la persistance au texte produit par `overview.build()`.

**API.** `run(book_id) -> str` — cache : `<id>_summary.json`.

**Particularité.** Son `cache_is_current` surveille les `mtime` de **six fichiers** (`summary.py`, `overview.py`, `metadata.py`, `entities.py`, `lexdiv.py`, `topics.py`) : le résumé étant une synthèse, il doit être régénéré dès qu'une de ses sources évolue.

---

## `modules/card.py` — book card

**Rôle.** Le livrable final : agréger les six analyses en un seul JSON.

**API.** `run(book_id) -> dict` — cache : `<id>_card.json`.

**Structure de sortie.**

```json
{
  "info":     { "id": "11", "title": "...", "authors": "...", "bookshelves": "..." },
  "lexdiv":   { "tok": 25412, "typ": 2548, ... },
  "topics":   { "1: nature": [...], "2: nature": [...], ... },
  "entities": { "characters": [...], "locations": [...] },
  "summary":  "Alice's Adventures in Wonderland, by Lewis Carroll, follows ...",
  "similar":  ["Through the Looking-Glass", ...]
}
```

**Fonctionnement.** `build_card` appelle simplement `metadata.info`, `lexdiv.run`, `topics.run`, `entities.run`, `summary.run` et `similarity.prepare + run`. Comme chaque sous-module est cache-first, la card ne recalcule jamais rien d'inutile : sur cache chaud, elle se résume à six lectures JSON. Sa validation de cache (`valid_cached_card`) vérifie le schéma complet, et son invalidation surveille les six modules sources — la card est toujours cohérente avec le code courant.
