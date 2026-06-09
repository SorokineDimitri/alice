# 📚 BookWorm — Moteur NLP de Book Cards

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![spaCy](https://img.shields.io/badge/spaCy-3.8-09A3D5?logo=spacy&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.5-F7931E?logo=scikitlearn&logoColor=white)
![Epitech](https://img.shields.io/badge/Epitech-Project-0091D0)

> **BookWorm** analyse n'importe quel livre du [Project Gutenberg](https://www.gutenberg.org/) et génère automatiquement sa *book card* : métriques lexicales, thèmes, personnages, lieux, résumé et œuvres similaires — **sans aucun LLM**, uniquement avec des techniques NLP classiques (TF-IDF, NER, lemmatisation, similarité cosinus, génération par gabarit).

---

## Sommaire

- [Aperçu](#aperçu)
- [Fonctionnalités](#fonctionnalités)
- [Démonstration](#démonstration)
- [Architecture](#architecture)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Structure du projet](#structure-du-projet)
- [Système de cache](#système-de-cache)
- [Stack technique](#stack-technique)
- [Tests](#tests)
- [Documentation détaillée](#documentation-détaillée)
- [Auteurs](#auteurs)

---

## Aperçu

BookWorm est un outil en ligne de commande qui prend en entrée un **identifiant de livre Project Gutenberg** (ex. `11` pour *Alice's Adventures in Wonderland*) et produit une analyse littéraire complète. Le projet repose sur un **pipeline modulaire** :

```
Téléchargement → Nettoyage → Analyses NLP → Synthèse → Book Card
```

Chaque étape est un module indépendant, mis en cache sur disque, et réutilisable par les étapes suivantes. L'intégralité de l'analyse est **déterministe et explicable** : aucun modèle génératif n'est utilisé, ce qui rend chaque résultat traçable jusqu'à la règle ou la statistique qui l'a produit.

## Fonctionnalités

| Commande | Module | Description |
|---|---|---|
| `--lexdiv ID` | [`modules/lexdiv.py`](modules/lexdiv.py) | 6 métriques de diversité lexicale (tokens, hapax, TTR…) |
| `--topics ID` | [`modules/topics.py`](modules/topics.py) | Thèmes dominants chapitre par chapitre via TF-IDF + dictionnaire de 147 thèmes littéraires |
| `--entities ID` | [`modules/entities.py`](modules/entities.py) | Personnages et lieux extraits par NER (spaCy) + règles contextuelles |
| `--summarize ID` | [`modules/summary.py`](modules/summary.py) | Résumé en langage naturel généré par gabarit (template NLG) |
| `--similar ID` | [`modules/similarity.py`](modules/similarity.py) | 5 livres les plus proches par similarité cosinus sur vecteurs TF-IDF |
| `--card ID` | [`modules/card.py`](modules/card.py) | **Book card complète** agrégeant toutes les analyses ci-dessus |

## Démonstration

Toutes les sorties ci-dessous sont de **vraies sorties** du programme pour *Alice's Adventures in Wonderland* (`ID 11`).

### Diversité lexicale

```console
$ python3 bookworm.py --lexdiv 11
{
  "tok": 25412,        // nombre total de mots (tokens)
  "typ": 2548,         // nombre de mots uniques (types)
  "hap": 1104,         // hapax : mots utilisés une seule fois
  "ttr": 0.1002,       // type-token ratio (richesse du vocabulaire)
  "mwl": 4.13,         // longueur moyenne d'un mot
  "mwf": 9.97          // fréquence moyenne d'un mot
}
```

### Personnages et lieux

```console
$ python3 bookworm.py --entities 11
{
  "characters": ["Alice", "Hatter", "Mouse", "Queen", "Bill", "Majesty", "King", ...],
  "locations":  ["Dinah", "England", "Wonderland"]
}
```

### Résumé généré

```console
$ python3 bookworm.py --summarize 11
Alice's Adventures in Wonderland, by Lewis Carroll, follows Alice, the main
character, alongside figures such as Hatter, Mouse and Queen, in Wonderland
serving as one of the important places in the story. Alice's Adventures in
Wonderland presents a narrative that gradually unfolds around nature, quest,
animal and rescue. Across its 12 chapters, the story moves from nature toward
madness.
```

### Livres similaires

```console
$ python3 bookworm.py --similar 11
[
  "Through the Looking-Glass",
  "Treasure Island",
  "The Secret Garden",
  "The Jungle Book",
  "Peter Pan"
]
```

## Architecture

Le projet est organisé en **trois couches** qui communiquent exclusivement via des fonctions `run(book_id)` et un cache JSON partagé :

```mermaid
flowchart TB
    CLI["bookworm.py<br/>(CLI argparse)"]

    subgraph ACQ["🌐 Couche acquisition"]
        GUT["gutenberg.py<br/>téléchargement HTTP"]
        PC["utils/path_config.py<br/>get_text / get_raw_text"]
        CLEANER["cleaner.py<br/>retrait en-têtes Gutenberg<br/>+ table des matières"]
    end

    subgraph ANALYSE["🔬 Couche analyse"]
        LEX["lexdiv.py<br/>métriques lexicales"]
        TOP["topics.py<br/>thèmes par TF-IDF"]
        ENT["entities.py<br/>NER personnages/lieux"]
        SIM["similarity.py<br/>similarité cosinus"]
    end

    subgraph SYNTH["📝 Couche synthèse"]
        META["utils/metadata.py<br/>titre / auteur / rayons"]
        OVR["overview.py<br/>génération par gabarit"]
        SUM["summary.py<br/>résumé + cache"]
        CARD["card.py<br/>agrégation finale"]
    end

    NLP["nlp.py<br/>TF-IDF · spaCy · lemmatisation<br/>(boîte à outils partagée)"]
    CACHE[("data/cache/*.json<br/>data/raw/*.txt")]

    CLI --> LEX & TOP & ENT & SUM & SIM & CARD
    PC --> GUT
    PC --> CLEANER
    LEX & TOP & ENT & SIM --> PC
    LEX & TOP & SIM --> NLP
    ENT --> NLP
    META --> TOP
    OVR --> ENT & TOP & META
    SUM --> OVR
    CARD --> META & LEX & TOP & ENT & SUM & SIM
    LEX & TOP & ENT & SIM & SUM & CARD <--> CACHE
```

**Lecture du graphe** : `--card` est le sommet de la pyramide — il appelle les 5 autres analyses, qui elles-mêmes s'appuient sur la boîte à outils `nlp.py` et la couche d'acquisition. Chaque module vérifie d'abord son cache avant de calculer.

➡️ L'architecture complète (diagrammes de séquence, algorithmes, choix de conception) est détaillée dans [`documentation/ARCHITECTURE.md`](documentation/ARCHITECTURE.md).

## Installation

**Prérequis** : Python ≥ 3.12

### Avec [uv](https://docs.astral.sh/uv/) (recommandé)

```bash
git clone <url-du-repo> bookworm && cd bookworm
uv sync
```

### Avec pip

```bash
git clone <url-du-repo> bookworm && cd bookworm
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> Le modèle spaCy `en_core_web_sm` est déclaré comme dépendance directe : il s'installe automatiquement, aucun `spacy download` manuel n'est nécessaire.

## Utilisation

```bash
python3 bookworm.py --card 11        # book card complète d'Alice au pays des merveilles
python3 bookworm.py --lexdiv 84      # diversité lexicale de Frankenstein
python3 bookworm.py --topics 1184    # thèmes du Comte de Monte-Cristo
python3 bookworm.py --help           # aide complète
```

Les options sont **mutuellement exclusives** : une commande = une analyse. L'`ID` correspond à l'identifiant du livre sur [gutenberg.org](https://www.gutenberg.org/) (visible dans l'URL de chaque livre).

- **Premier lancement** : le texte est téléchargé puis analysé (l'analyse spaCy peut prendre quelques dizaines de secondes sur un gros livre).
- **Lancements suivants** : la réponse est instantanée grâce au [cache](#système-de-cache).

## Structure du projet

```
.
├── bookworm.py              # Point d'entrée CLI (argparse + dispatch dynamique)
├── modules/
│   ├── gutenberg.py         # Téléchargement HTTP depuis Project Gutenberg
│   ├── cleaner.py           # Nettoyage : en-têtes Gutenberg, table des matières
│   ├── nlp.py               # Outils NLP partagés : TF-IDF, spaCy, lemmatisation
│   ├── cache.py             # Lecture/écriture JSON avec validation
│   ├── lexdiv.py            # Métriques de diversité lexicale
│   ├── topics.py            # Extraction de thèmes (TF-IDF par section)
│   ├── entities.py          # NER : personnages et lieux (spaCy + règles)
│   ├── overview.py          # Génération de phrases par gabarit (NLG)
│   ├── summary.py           # Orchestration + cache du résumé
│   ├── similarity.py        # Livres similaires (cosinus + bonus catégorie)
│   └── card.py              # Agrégation : la book card finale
├── utils/
│   ├── path_config.py       # Chemins + accès texte (brut / nettoyé)
│   └── metadata.py          # Extraction titre / auteur depuis l'en-tête
├── data/
│   ├── literary_themes.json # Dictionnaire de 147 thèmes littéraires
│   ├── entity_rules.json    # Règles linguistiques pour la détection de lieux
│   ├── similar_books.json   # Catalogue de 21 livres de référence (3 catégories)
│   ├── raw/                 # Textes bruts téléchargés (cache niveau 1)
│   └── cache/               # Résultats d'analyse JSON (cache niveau 2)
├── documentation/           # Documentation technique détaillée
├── test_gutenberg.py        # Tests du module de téléchargement
├── pyproject.toml           # Dépendances (gérées par uv)
└── requirements.txt         # Dépendances (format pip)
```

## Système de cache

Le cache fonctionne sur **deux niveaux** et rend toute analyse répétée instantanée :

```mermaid
flowchart LR
    A["run(book_id)"] --> B{"Cache JSON<br/>valide et à jour ?"}
    B -- oui --> C["✅ Retour immédiat"]
    B -- non --> D{"Texte brut<br/>sur disque ?"}
    D -- non --> E["Téléchargement<br/>Gutenberg"]
    E --> F["data/raw/ID.txt"]
    D -- oui --> F
    F --> G["Nettoyage + Analyse NLP"]
    G --> H["data/cache/ID_tâche.json"]
    H --> C
```

Trois garde-fous évitent de servir un résultat périmé ou corrompu :

1. **Validation de schéma** — chaque module vérifie la structure du JSON (clés requises, types) avant de le servir ;
2. **Invalidation par date** — si le code du module (ou un fichier de données dont il dépend) est plus récent que le cache, l'analyse est recalculée ;
3. **Écriture atomique par tâche** — un fichier par couple `(livre, tâche)` : `11_topics.json`, `11_entities.json`…

## Stack technique

| Outil | Rôle | Pourquoi ce choix |
|---|---|---|
| **spaCy** (`en_core_web_sm`) | NER, lemmatisation, POS-tagging | Pipeline industriel, rapide, modèle léger suffisant pour de la littérature anglaise |
| **scikit-learn** | `TfidfVectorizer`, `cosine_similarity` | Implémentations de référence, vecteurs creux efficaces sur des livres entiers |
| **requests** | Téléchargement HTTP | Simplicité, gestion d'erreurs propre |
| **asyncio** | Téléchargements concurrents (`--similar`) | 21 livres téléchargés 4 par 4 au lieu de séquentiellement |
| **argparse** | Interface CLI | Bibliothèque standard, zéro dépendance |
| **uv** | Gestion des dépendances | Lockfile reproductible, installation du modèle spaCy déclarative |

**Parti pris fort** : aucun LLM, aucun appel API d'IA. Toutes les analyses sont fondées sur des statistiques (TF-IDF, comptages) et des règles linguistiques explicites — chaque résultat est **explicable et reproductible**.

## Tests

```bash
.venv/bin/python3 test_gutenberg.py
```

Vérifie le téléchargement (livre existant, second miroir, livre inexistant → erreur propre).

## Documentation détaillée

| Document | Contenu |
|---|---|
| [`documentation/ARCHITECTURE.md`](documentation/ARCHITECTURE.md) | Pipeline complet, diagrammes de séquence, système de cache, choix de conception et compromis |
| [`documentation/MODULES.md`](documentation/MODULES.md) | Référence module par module : rôle, API, algorithme, exemples |

## Auteurs

Projet réalisé dans le cadre du cursus **Epitech**.

- **Driss Costa** — [@Driss2003costa](https://github.com/Driss2003costa)
- **Dimitri Sorokine** — [@SorokineDimitri](https://github.com/SorokineDimitri)
