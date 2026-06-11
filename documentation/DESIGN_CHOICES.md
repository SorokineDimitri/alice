# Choix de conception et compromis

Ce document complète [`ARCHITECTURE.md`](ARCHITECTURE.md). Il explique les arbitrages techniques du projet BookWorm : pourquoi certaines approches ont été retenues et pourquoi d'autres ont été écartées.

## 1. Topics : TF-IDF + dictionnaire plutôt que LDA / LSA / Empath

Objectif du module `topics.py` : produire des thèmes lisibles par section, sous une forme directement exploitable dans la book card :

```text
section du livre -> thème nommé -> 10 mots représentatifs
```

Pipeline retenu :

```text
texte nettoyé -> découpage par chapitres/sections -> lemmatisation spaCy -> TF-IDF par section -> scoring sur data/literary_themes.json -> thème + mots
```

Pourquoi TF-IDF :

- TF-IDF fait ressortir les mots spécifiques à une section, pas seulement les mots fréquents dans tout le livre.
- Le résultat reste explicable : un thème est choisi parce que ses mots du dictionnaire ont un poids TF-IDF fort.
- Le calcul est léger et fonctionne sans modèle lourd.
- Le résultat est stable : même entrée -> même sortie.

Pourquoi un dictionnaire littéraire custom :

- Le projet demande des thèmes compréhensibles pour un lecteur ou un éditeur, pas seulement des clusters mathématiques.
- Le dictionnaire force les sorties vers des labels lisibles : `nature`, `madness`, `revenge`, `detective`, etc.
- Il évite les thèmes trop abstraits ou inutilisables dans la card.

Pourquoi LDA a été écarté :

- LDA donne des groupes de mots, mais pas un nom de thème fiable.
- Les topics LDA peuvent mélanger des mots narratifs très génériques (`said`, `time`, `man`, `come`) avec des mots de sujet.
- Les résultats sont difficiles à expliquer à l'utilisateur final : un topic LDA est une distribution probabiliste, pas une catégorie littéraire claire.
- Sur des romans découpés en peu de sections, LDA est instable et dépend beaucoup du nombre de topics choisi.
- Pour notre objectif, LDA répond plutôt à “quels mots co-occurrent ?” qu'à “quel thème littéraire ressort ?”.

Pourquoi LSA a été écarté :

- LSA produit des dimensions latentes qui ne sont pas directement nommables.
- Les composantes sont utiles pour la recherche/similarité, mais moins pour générer une sortie du type `1: nature -> [word1, ...]`.
- Comme LDA, il faut ensuite inventer une étape de labellisation, ce qui rend le système moins explicable.

Pourquoi Empath a été écarté :

- Empath est intéressant pour associer des mots à des catégories sémantiques, mais ses catégories ne sont pas toujours adaptées à la littérature classique.
- Nous avions besoin d'un vocabulaire de thèmes contrôlé et orienté livres : aventure, enquête, vengeance, nature, enfance, etc.
- Le dictionnaire custom est plus transparent : on sait exactement quels mots influencent chaque thème.
- Empath ajoutait une dépendance et une logique de scoring supplémentaire sans donner des résultats plus fiables sur nos exemples.

Compromis accepté :

- Le résultat dépend de la qualité de `data/literary_themes.json`.
- Un thème peut être imparfait si le dictionnaire manque de vocabulaire ou si une section contient peu de mots discriminants.
- En échange, le module reste lisible, déterministe, léger et facile à ajuster.

## 2. Entities : spaCy + règles custom plutôt que spaCy seul

Objectif du module `entities.py` : extraire deux listes simples et utiles :

```json
{
  "characters": [...],
  "locations": [...]
}
```

Pipeline retenu :

```text
texte nettoyé -> échantillonnage si gros livre -> spaCy NER/POS/deps -> règles contextuelles -> scoring -> top personnages/lieux
```

Pourquoi utiliser spaCy :

- spaCy fournit déjà la tokenisation, les entités nommées, les POS tags et les dépendances grammaticales.
- Réimplémenter tout cela avec des regex serait très bruité.
- Le modèle `en_core_web_sm` reste assez léger pour le projet.

Pourquoi spaCy seul ne suffit pas :

- spaCy confond souvent certains personnages et lieux dans les romans.
- Des noms comme `Paris`, `France`, `White Fang`, `Monte Cristo`, `King`, `Queen` peuvent être mal classés selon le contexte.
- Les livres contiennent des titres de chapitres, dialogues, possessifs et noms composés qui créent du bruit.
- La sortie brute de spaCy n'est pas directement exploitable comme liste éditoriale propre.

Règles ajoutées autour de spaCy :

- Prioriser les entités `PERSON` pour les personnages.
- Utiliser le contexte grammatical pour savoir si une entité agit comme un personnage.
- Utiliser les prépositions de lieu pour renforcer les lieux.
- Filtrer les faux lieux avec `data/entity_rules.json` (`non_location_nouns`, `location_nouns`).
- Détecter certains lieux possessifs seulement si le nom est un vrai nom de lieu générique (`house`, `room`, `garden`, `palace`, etc.).
- Promouvoir le personnage principal si son nom apparaît dans le titre (`White Fang`, `Monte Cristo`).

Pourquoi ne pas utiliser uniquement des regex :

- Les regex sur majuscules capturent trop de bruit : titres de chapitres, débuts de phrases, noms communs capitalisés, dialogues.
- Elles ne savent pas distinguer une personne d'un lieu sans contexte grammatical.
- Elles demanderaient beaucoup de règles spécifiques par livre, ce que nous voulons éviter.

Pourquoi ne pas utiliser une bibliothèque plus lourde :

- Stanza, Flair ou des modèles Transformers amélioreraient peut-être certains cas, mais augmenteraient fortement le temps d'installation et d'exécution.
- Le projet doit rester simple à lancer sur plusieurs machines avec `uv sync`.
- Le gain qualitatif ne justifie pas la complexité pour une sortie limitée à 20 personnages et 20 lieux.

Compromis accepté :

- La sortie peut encore contenir du bruit, surtout pour les lieux.
- En échange, la méthode est rapide, explicable et assez robuste sur plusieurs livres sans règles spécifiques à un roman.

## 3. Échantillonnage des entités sur les gros livres

Problème observé : sur un gros livre comme *The Count of Monte Cristo*, passer tout le texte dans spaCy coûtait trop cher.

Approche retenue :

```text
si texte <= 750 000 caractères -> analyser tout le texte
sinon -> analyser 250k début + 250k milieu + 250k fin
```

Pourquoi :

- Les personnages principaux apparaissent généralement à plusieurs moments du livre.
- Le début, le milieu et la fin donnent une couverture raisonnable du récit.
- Le temps de calcul diminue fortement (jusqu'à 50 %) sans ajouter de cache intermédiaire complexe.

Compromis accepté :

- Un personnage secondaire important mais présent seulement dans une zone non échantillonnée peut être raté.
- Pour une book card synthétique, la priorité est d'extraire les figures dominantes, pas tous les personnages.

## 4. Résumé : gabarit plutôt que résumé extractif ou LLM

Objectif du résumé : produire un court texte lisible pour la book card, sans relire manuellement le livre et sans dépendre d'un service externe.

Le sujet demandait d'explorer plusieurs approches :

- méthodes extractives : TextRank, clustering, sélection de phrases importantes ;
- méthodes abstractives légères si possible ;
- justification du choix final, de ses limites et des alternatives.

Pipeline retenu :

```text
metadata + entities + topics -> overview.py -> phrase générée par gabarit -> summary.py -> cache
```

Méthode retenue : résumé abstractif léger par gabarit.

Le résumé n'est pas généré en inventant du contenu librement. Il assemble une phrase synthétique à partir de résultats déjà calculés :

- `metadata` fournit le titre et l'auteur ;
- `entities` fournit le personnage principal, les personnages secondaires et le lieu dominant ;
- `topics` fournit les thèmes dominants et l'évolution thématique du livre ;
- `summary.py` met le résultat en cache.

Exemple de logique :

```text
titre + auteur + personnage principal + lieu principal + thèmes dominants + évolution des thèmes
```

Pourquoi cette méthode :

- Elle donne un texte plus fluide qu'une simple liste de mots-clés.
- Elle reste légère : pas de modèle de langage lourd, pas d'API externe, pas de GPU.
- Elle est déterministe : même livre -> même résumé.
- Elle est explicable : chaque morceau du résumé vient d'un module identifiable.
- Elle correspond mieux à une book card qu'un extrait brut du roman.

Alternatives extractives considérées :

- TextRank : sélectionner les phrases les plus centrales du texte.
- Clustering : regrouper les phrases puis choisir une phrase représentative par groupe.
- TF-IDF sur les phrases : garder les phrases avec les mots les plus discriminants.

Pourquoi nous n'avons pas retenu l'extractif :

- L'ancien résumé sélectionnait des phrases “fortes” du livre avec TF-IDF/TextRank.
- Les phrases extraites étaient parfois longues, dialoguées, coupées ou trop contextuelles.
- Le résultat ressemblait à une collection de citations, pas à un vrai résumé de book card.
- Pour les gros livres, le découpage et le scoring des phrases ajoutaient du temps de calcul.
- Les romans Gutenberg contiennent beaucoup de dialogues, titres, préfaces et phrases anciennes qui ne résument pas toujours bien le livre.

Alternatives abstractives considérées :

- Modèle local de résumé : trop lourd à installer et exécuter pour un projet qui doit rester simple avec `uv sync`.
- Génération libre à partir du texte : risque d'hallucination et difficile à justifier.

Limites de notre choix :

- Le résumé est analytique, pas un résumé narratif détaillé de l'intrigue.
- Il décrit les thèmes, personnages et lieux dominants plutôt que les événements précis scène par scène.
- Si `entities` ou `topics` se trompent, le résumé hérite de cette erreur.
- Le style est contrôlé mais moins riche qu'un vrai résumé humain.
- Le gabarit ne sait pas raconter précisément les rebondissements, les relations ou la fin du livre.

Compromis accepté :

- On préfère un résumé court, stable, rapide et justifiable plutôt qu'un résumé plus ambitieux mais bruité ou difficile à reproduire.
- Pour une book card, ce compromis est cohérent : le but est de donner une vue d'ensemble éditoriale, pas de remplacer une analyse littéraire complète.

## 5. Similarité : TF-IDF + bonus catégorie plutôt que TF-IDF pur (similarité cosinus proposé)

Objectif du module `similarity.py` : proposer 5 livres proches à partir d'un catalogue contrôlé (`data/similar_books.json`).

Première approche :

```text
texte des livres -> TF-IDF -> similarité cosinus -> top 5
```

Problème observé :

- Pour Alice (`ID 11`), TF-IDF pur rapprochait trop fortement Sherlock Holmes ou Dracula.
- Ce score capturait surtout le vocabulaire et le style, pas le public cible ou le genre éditorial.
- Or `Peter Pan` doit intuitivement être plus proche d'Alice que Sherlock ou Dracula.

Approche retenue :

```text
score final = similarité TF-IDF + bonus si même catégorie éditoriale
```

Pourquoi :

- TF-IDF garde une mesure textuelle réelle.
- Le bonus catégorie injecte une information éditoriale simple : jeunesse, policier, science-fiction/fantasy.
- Le résultat correspond mieux aux attentes d'une book card.

Compromis accepté :

- Le score dépend du catalogue `similar_books.json`.
- Un livre mal catégorisé peut être favorisé à tort.
- En échange, le résultat est plus cohérent pour l'utilisateur final.

## 6. Métadonnées : extraction depuis le texte brut plutôt que RDF Gutenberg

Nous avions une version qui lisait les métadonnées RDF de Gutenberg. Elle a été remplacée par `utils/metadata.py`, qui extrait titre et auteur depuis le texte brut.

Pourquoi :

- Le projet part du principe que l'entrée principale est le fichier texte Gutenberg.
- Scraper une autre ressource RDF/HTML ajoute une dépendance réseau et une logique externe au livre analysé.
- Le titre et l'auteur sont généralement présents dans l'en-tête du `.txt`.
- Les `bookshelves` sont désormais produits par nos propres topics, ce qui reste cohérent avec l'analyse NLP.

Compromis accepté :

- Les en-têtes Gutenberg ne sont pas parfaitement uniformes.
- L'extraction titre/auteur peut nécessiter des heuristiques (`by`, `Author:`, `BY`, etc.).
- En échange, la card est construite à partir du même texte que le reste de l'analyse.

## 7. Cache final plutôt que cache intermédiaire

Nous avons testé un cache intermédiaire (`data/temp_cache`) pour le texte nettoyé, les lemmes et les phrases.

Pourquoi il a été retiré :

- Dans l'usage réel, si un résultat final existe (`ID_topics.json`, `ID_summary.json`, etc.), le cache intermédiaire ne sert pas.
- Le cas “cache intermédiaire présent mais cache final absent” est rare, voire quasi impossible.
- Il ajoutait des fichiers, de l'invalidation et de la complexité sans gain suffisant sur le workflow normal.

Approche retenue :

```text
cache raw -> data/raw/ID.txt
cache final -> data/cache/ID_task.json
```

Compromis accepté :

- Si on supprime seulement les caches finaux, certains calculs lourds doivent être refaits.
- En échange, le système de cache reste simple, lisible et facile à expliquer.
