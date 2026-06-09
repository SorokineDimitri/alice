# Architecture de BookWorm

Ce document décrit l'architecture complète du projet : le pipeline de traitement, la communication entre les fichiers, le système de cache et les choix de conception. Pour la référence détaillée de chaque module (API, algorithmes), voir [`MODULES.md`](MODULES.md).

## Sommaire

- [1. Vue d'ensemble](#1-vue-densemble)
- [2. Principes de conception](#2-principes-de-conception)
- [3. Le pipeline de bout en bout](#3-le-pipeline-de-bout-en-bout)
- [4. Communication entre les fichiers](#4-communication-entre-les-fichiers)
- [5. Déroulé complet d'un `--card`](#5-déroulé-complet-dun---card)
- [6. Le système de cache](#6-le-système-de-cache)
- [7. Les fichiers de données](#7-les-fichiers-de-données)
- [8. Choix de conception et compromis](#8-choix-de-conception-et-compromis)

---

## 1. Vue d'ensemble

BookWorm est structuré comme un **pipeline en couches**. Chaque couche ne connaît que la couche en dessous d'elle :

```mermaid
flowchart TB
    L0["<b>Couche 0 — Interface</b><br/>bookworm.py"]
    L1["<b>Couche 1 — Synthèse</b><br/>card.py · summary.py · overview.py · metadata.py"]
    L2["<b>Couche 2 — Analyse</b><br/>lexdiv.py · topics.py · entities.py · similarity.py"]
    L3["<b>Couche 3 — Outils partagés</b><br/>nlp.py · cache.py · path_config.py"]
    L4["<b>Couche 4 — Acquisition</b><br/>gutenberg.py · cleaner.py"]
    EXT[("Project Gutenberg<br/>gutenberg.org")]

    L0 --> L1
    L0 --> L2
    L1 --> L2
    L2 --> L3
    L1 --> L3
    L3 --> L4
    L4 --> EXT
```

| Couche | Responsabilité | Fichiers |
|---|---|---|
| **Interface** | Parser les arguments, dispatcher vers le bon module, formater la sortie | `bookworm.py` |
| **Synthèse** | Combiner les analyses en livrables lisibles (résumé, book card) | `card.py`, `summary.py`, `overview.py`, `utils/metadata.py` |
| **Analyse** | Une analyse NLP = un module, indépendant des autres | `lexdiv.py`, `topics.py`, `entities.py`, `similarity.py` |
| **Outils partagés** | Code mutualisé : vectorisation, spaCy, cache JSON, chemins | `nlp.py`, `cache.py`, `utils/path_config.py` |
| **Acquisition** | Obtenir un texte propre à partir d'un simple ID | `gutenberg.py`, `cleaner.py` |

## 2. Principes de conception

Quatre principes structurent tout le code :

1. **Une interface unique : `run(book_id)`.** Chaque module d'analyse expose une fonction `run(book_id)` qui retourne un résultat sérialisable en JSON. Le CLI dispatche dynamiquement vers le bon module (`bookworm.py:53-64`) sans connaître son implémentation. Ajouter une nouvelle analyse = créer un module avec un `run()` et l'enregistrer dans `TASK_MODULES`.

2. **Cache-first.** Chaque `run()` commence par tenter de servir le cache. Le calcul est l'exception, pas la règle. Voir [section 6](#6-le-système-de-cache).

3. **Composition plutôt que duplication.** Les modules de synthèse ne recalculent rien : `overview.py` appelle `entities.run()`, `topics.run()` et `metadata.info()` ; `card.py` appelle les 6 analyses. Comme chacune est cachée, l'agrégation est quasi gratuite.

4. **Zéro IA générative.** Le résumé est produit par **gabarit** (phrases à trous remplies avec les résultats d'analyse). Les thèmes viennent d'un **dictionnaire littéraire** croisé avec des poids TF-IDF. Tout résultat est traçable jusqu'à la statistique ou la règle qui l'a produit — ce qui rend le système explicable, déterministe et léger (aucun GPU, aucun appel API).

## 3. Le pipeline de bout en bout

Tout livre suit le même chemin, quelle que soit l'analyse demandée :

```mermaid
flowchart LR
    ID(["book_id<br/>ex: 11"]) --> DL

    subgraph S1["1 · Acquisition"]
        DL["gutenberg.download()<br/>2 miroirs HTTP essayés"]
        RAW[("data/raw/11.txt")]
        DL --> RAW
    end

    subgraph S2["2 · Nettoyage"]
        CL["cleaner.clean()"]
        CL2["• retire l'en-tête légal Gutenberg<br/>(*** START/END OF ***)<br/>• retire la table des matières<br/>• commence au vrai chapitre 1"]
        CL --- CL2
    end

    subgraph S3["3 · Analyse NLP"]
        AN["lexdiv / topics /<br/>entities / similarity"]
    end

    subgraph S4["4 · Synthèse"]
        SY["overview / summary / card"]
    end

    OUT(["JSON ou texte<br/>sur stdout"])

    RAW --> CL --> AN --> SY --> OUT
    AN -.->|"cache JSON"| C[("data/cache/")]
    SY -.->|"cache JSON"| C
```

**Étape 1 — Acquisition** (`modules/gutenberg.py`). Le texte est téléchargé en essayant deux formats d'URL de Gutenberg (les livres ne sont pas tous hébergés au même endroit). Le texte brut est écrit dans `data/raw/<id>.txt` et ne sera plus jamais retéléchargé.

**Étape 2 — Nettoyage** (`modules/cleaner.py`). Les fichiers Gutenberg contiennent un en-tête légal, parfois des crédits d'illustration et une table des matières. Le nettoyeur :
- coupe tout ce qui précède `*** START OF ...` et suit `*** END OF ...` ;
- détecte les titres de chapitre (`CHAPTER I`, `LETTER 1`, `PART IV`…) et saute à la **deuxième occurrence** du premier titre — la première occurrence étant l'entrée de la table des matières, la deuxième le vrai début du récit.

**Étape 3 — Analyse**. Quatre analyses indépendantes, chacune dans son module (détails dans [`MODULES.md`](MODULES.md)) :

| Analyse | Technique principale |
|---|---|
| `lexdiv` | Tokenisation scikit-learn + comptages (`Counter`) |
| `topics` | Découpage en chapitres → lemmatisation spaCy → TF-IDF par section → mapping sur un dictionnaire de 147 thèmes |
| `entities` | NER spaCy + apprentissage de règles propres au livre + scoring contextuel |
| `similar` | TF-IDF sur un corpus de 21 livres + similarité cosinus + bonus de catégorie |

**Étape 4 — Synthèse**. `overview.py` assemble des phrases à partir des métadonnées, entités et thèmes ; `summary.py` y ajoute le cache ; `card.py` agrège les six résultats en un seul JSON.

## 4. Communication entre les fichiers

Le graphe ci-dessous montre **qui importe qui** (flèche = « dépend de »). C'est la carte de référence pour naviguer dans le code :

```mermaid
flowchart TB
    BW["bookworm.py"]

    subgraph synthese["Synthèse"]
        CARD["card.py"]
        SUM["summary.py"]
        OVR["overview.py"]
        META["utils/metadata.py"]
    end

    subgraph analyse["Analyse"]
        LEX["lexdiv.py"]
        TOP["topics.py"]
        ENT["entities.py"]
        SIM["similarity.py"]
    end

    subgraph outils["Outils partagés"]
        NLP["nlp.py"]
        CACHE["cache.py"]
        PC["utils/path_config.py"]
    end

    subgraph acquisition["Acquisition"]
        GUT["gutenberg.py"]
        CLEAN["cleaner.py"]
    end

    subgraph data["data/"]
        THEMES[/"literary_themes.json"/]
        RULES[/"entity_rules.json"/]
        BOOKS[/"similar_books.json"/]
    end

    BW -.->|"import dynamique"| LEX & TOP & ENT & SUM & SIM & CARD

    CARD --> META & LEX & TOP & ENT & SUM & SIM
    SUM --> OVR
    OVR --> ENT & TOP & META
    META --> TOP & PC
    META --> CLEAN

    LEX --> NLP & CACHE & PC
    TOP --> NLP & CACHE & PC
    TOP --> THEMES
    ENT --> NLP & CACHE & PC & META
    ENT --> RULES
    SIM --> NLP & CACHE & PC & GUT
    SIM --> BOOKS

    PC --> CLEAN & GUT
```

Points notables :

- **`bookworm.py` ne fait aucun `import` en dur des modules d'analyse** : il utilise `__import__("modules." + nom)` à partir de la table `TASK_MODULES`. Le CLI reste donc à 70 lignes et n'a pas besoin d'être modifié quand un module évolue.
- **`nlp.py` est la seule porte d'entrée vers spaCy et TF-IDF.** Le modèle spaCy est chargé une seule fois par configuration grâce à `functools.lru_cache` — un chargement coûte ~1 s, le partager entre modules est essentiel.
- **`utils/path_config.py` est le point de convergence de l'acquisition** : `get_raw_text()` (télécharge si absent, sinon lit le disque) et `get_text()` (pareil + nettoyage). Aucun module d'analyse ne parle directement à `gutenberg.py`, sauf `similarity.py` qui a besoin de téléchargements concurrents.
- **Dépendance croisée contrôlée** : `metadata.py` (couche synthèse) appelle `topics.run()` pour remplir le champ `bookshelves` à partir des thèmes détectés. C'est la seule remontée de ce type, et elle reste sans cycle.

## 5. Déroulé complet d'un `--card`

Le diagramme de séquence ci-dessous montre tous les échanges pour `python3 bookworm.py --card 11` **sur un cache froid** (premier lancement) :

```mermaid
sequenceDiagram
    actor U as Utilisateur
    participant BW as bookworm.py
    participant CARD as card.py
    participant AN as lexdiv / topics / entities
    participant SUM as summary.py → overview.py
    participant SIM as similarity.py
    participant PC as path_config.py
    participant GB as gutenberg.org
    participant FS as data/ (disque)

    U->>BW: --card 11
    BW->>CARD: run(11)
    CARD->>FS: cache 11_card.json ?
    FS-->>CARD: absent

    Note over CARD,AN: metadata.info(11) puis chaque analyse,<br/>chacune cache-first
    CARD->>AN: run(11)
    AN->>PC: get_text(11)
    PC->>GB: GET /files/11/11-0.txt
    GB-->>PC: texte brut
    PC->>FS: écrit data/raw/11.txt
    PC-->>AN: texte nettoyé (cleaner.clean)
    AN->>FS: écrit 11_lexdiv.json, 11_topics.json, 11_entities.json
    AN-->>CARD: métriques, thèmes, entités

    CARD->>SUM: run(11)
    Note over SUM: relit entities/topics/metadata<br/>depuis le cache (instantané)
    SUM->>FS: écrit 11_summary.json
    SUM-->>CARD: résumé

    CARD->>SIM: prepare(11) + run(11)
    SIM->>GB: télécharge le corpus manquant<br/>(asyncio, 4 en parallèle)
    SIM->>FS: écrit 11_similar.json
    SIM-->>CARD: 5 titres similaires

    CARD->>FS: écrit 11_card.json
    CARD-->>BW: book card complète
    BW-->>U: JSON indenté sur stdout
```

Au **second lancement**, la séquence se réduit à : `card.run(11)` → lecture de `11_card.json` → validation → retour. Aucun téléchargement, aucun calcul spaCy.

## 6. Le système de cache

### Deux niveaux

| Niveau | Emplacement | Contenu | Évite |
|---|---|---|---|
| 1 — Texte brut | `data/raw/<id>.txt` | Le fichier Gutenberg tel quel | Le réseau |
| 2 — Résultats | `data/cache/<id>_<tâche>.json` | Le résultat d'une analyse | Le calcul NLP |

### Cycle de décision

Chaque `run()` suit exactement la même logique :

```mermaid
flowchart TD
    A["run(book_id)"] --> B{"Le fichier cache<br/>existe-t-il ?"}
    B -- non --> CALC
    B -- oui --> C{"JSON bien formé<br/>et schéma valide ?"}
    C -- non --> CALC
    C -- oui --> D{"Cache plus récent que<br/>le code du module et<br/>ses fichiers de données ?"}
    D -- non --> CALC
    D -- oui --> OK["✅ Servir le cache"]
    CALC["Recalculer"] --> SAVE["save_json()"] --> RET["Retourner le résultat"]
```

### Les trois garde-fous

1. **Validation de schéma** — `cache.load_json()` rejette tout JSON mal formé ; chaque module ajoute sa propre validation structurelle (`valid_cached_topics`, `valid_cached_entities`, `valid_cached_card`…). Un cache écrit par une ancienne version du code, ou corrompu, est silencieusement recalculé.

2. **Invalidation par `mtime`** — la fonction `cache_is_current()` de chaque module compare la date du cache à celle **du code et des fichiers de données dont le résultat dépend**. Exemple pour `card.py` : le cache de la card est invalidé si *n'importe lequel* des 6 modules sous-jacents a été modifié depuis. C'est un mécanisme du type *Makefile* : modifier `topics.py` régénère automatiquement les topics, les résumés et les cards au prochain appel, sans rien supprimer à la main.

3. **Granularité par tâche** — un fichier par couple (livre, analyse). Invalider les topics ne touche pas aux entités déjà calculées.

### Chaîne d'invalidation

```mermaid
flowchart BT
    THEMES[/"literary_themes.json"/] --> TOPC[("11_topics.json")]
    TOPPY["topics.py"] --> TOPC
    RULES[/"entity_rules.json"/] --> ENTC[("11_entities.json")]
    ENTPY["entities.py"] --> ENTC
    METAPY["metadata.py"] --> ENTC
    BOOKS[/"similar_books.json"/] --> SIMC[("11_similar.json")]
    SIMPY["similarity.py"] --> SIMC
    TOPC & ENTC --> SUMC[("11_summary.json")]
    OVRPY["overview.py"] --> SUMC
    SUMC & TOPC & ENTC & SIMC & LEXC[("11_lexdiv.json")] --> CARDC[("11_card.json")]
```

*Lire de bas en haut : si un nœud source change, tous les caches au-dessus sont régénérés au prochain appel.*

## 7. Les fichiers de données

Le comportement linguistique du moteur est **externalisé dans trois fichiers JSON** — on peut affiner les résultats sans toucher au code Python :

| Fichier | Taille | Rôle | Consommé par |
|---|---|---|---|
| `data/literary_themes.json` | 147 thèmes | Dictionnaire `thème → mots-clés` (ex. `"adventure": ["quest", "journey", ...]`). Sert à nommer les topics TF-IDF. | `topics.py` |
| `data/entity_rules.json` | 3 listes (320 entrées) | Règles linguistiques pour la détection de lieux : prépositions locatives (`in`, `at`, `near`…), noms génériques de lieux (`castle`, `garden`…), faux positifs à exclure (`voice`, `heart`…). | `entities.py` |
| `data/similar_books.json` | 21 livres | Corpus de référence pour `--similar` : id Gutenberg, titre, catégorie (3 catégories : jeunesse, policier, SF/fantasy). | `similarity.py` |

Tous trois sont chargés une seule fois par processus via `functools.lru_cache`, et leur `mtime` participe à l'invalidation du cache (modifier le dictionnaire de thèmes recalcule les topics).

## 8. Choix de conception et compromis

Cette section documente les arbitrages techniques — utile pour comprendre *pourquoi* le code est écrit ainsi.

### TF-IDF + dictionnaire plutôt que LDA / embeddings (topics)

Une modélisation de sujets classique (LDA) produit des sacs de mots difficiles à nommer (« topic 3 : pool, dog, water… »). Notre approche en deux temps — TF-IDF pour trouver les mots saillants de chaque chapitre, puis projection sur un dictionnaire littéraire de 147 thèmes — produit des **labels lisibles** (« nature », « quest », « madness ») et un **arc narratif** (le thème de chaque chapitre, dans l'ordre). Compromis : les thèmes possibles sont bornés par le dictionnaire ; un thème absent du dictionnaire retombe sur `general`.

### Découpage par chapitres avec repli (topics)

Les sections suivent d'abord les **titres posés par l'auteur** (`CHAPTER I`, sections en chiffres romains) — c'est le découpage thématique le plus fidèle. Si aucun titre n'est détecté, repli sur des blocs de 1 500 lemmes. Les sections de moins de 80 mots (pages de titre résiduelles) sont écartées.

### NER hybride : modèle + règles apprises par livre (entities)

`en_core_web_sm` seul produit beaucoup de faux positifs sur la littérature du XIXᵉ (personnification d'animaux, majuscules archaïques). Le module corrige en **trois passes** sur le même document analysé :
1. **Apprentissage propre au livre** : un nom n'est retenu comme personnage que s'il apparaît au moins 2 fois en position d'acteur (sujet/objet d'un verbe). Cela permet de garder « Mouse » ou « Hatter » dans *Alice* (où les animaux *sont* des personnages) tout en les rejetant dans un roman réaliste.
2. **Comptage avec bonus contextuel** : chaque occurrence vaut 1 point, +1 si le contexte le confirme (verbe d'action pour un personnage, préposition locative pour un lieu).
3. **Arbitrage personnage/lieu** : un nom détecté à la fois comme PERSON et comme lieu est tranché par comparaison des scores — un nom plus souvent vu comme personne que comme lieu est écarté de la liste des lieux.
Enfin, le personnage qui apparaît dans le **titre du livre** est promu en tête de liste.

### Échantillonnage des gros livres (entities)

La NER spaCy est la passe la plus coûteuse du projet. Au-delà de 750 000 caractères, le module analyse un **échantillon début + milieu + fin** (3 × 250 000 caractères) : les personnages principaux d'un roman apparaissent dans ces trois zones, et le temps d'analyse devient borné quel que soit le livre. Compromis assumé : un personnage qui n'existerait qu'au cœur d'un très long roman peut être manqué.

### Génération par gabarit plutôt qu'un modèle de langue (summary)

Le « résumé » est une **génération par gabarit (template NLG)** : des phrases à trous remplies avec le titre, l'auteur, les personnages, le lieu principal et l'arc thématique chapitre par chapitre. Avantages : exécution en millisecondes, zéro hallucination, sortie 100 % traçable. Limite assumée : le texte est formulaïque — c'est une fiche de lecture, pas une prose originale.

### Similarité : cosinus + bonus de catégorie (similar)

La similarité lexicale pure (cosinus sur TF-IDF) rapproche parfois deux livres pour de mauvaises raisons (vocabulaire d'époque commun). Un **bonus fixe de +0,15** est ajouté quand les deux livres partagent la même catégorie éditoriale dans le catalogue. Les 21 livres du corpus sont téléchargés en concurrence (asyncio, 4 simultanés) uniquement lors du premier `--similar`.

### Import dynamique dans le CLI

`bookworm.py` résout le module à exécuter par `__import__` à partir d'une simple table nom → module. Conséquences : le CLI ne charge **que** le module demandé (lancer `--lexdiv` n'importe jamais spaCy NER), et l'ajout d'une analyse ne demande qu'une ligne dans `TASK_MODULES` plus une option argparse.
