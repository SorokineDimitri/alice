
from math import ceil

from sklearn.decomposition import NMF

from modules.cache import load_json, save_json
from modules.nlp import lemmatize, vectorize
from utils.path_config import cache_path, get_text

NB_THEMES = 5            # combien de themes on veut trouver
MOTS_PAR_THEME = 10     # combien de mots on garde pour decrire chaque theme
TAILLE_TRANCHE = 1500    # taille visee d'une tranche, en mots
MIN_TRANCHES = 4         # au moins 4 tranches, sinon la NMF n'a pas assez a comparer
MAX_RATIO = 0.8

# Si on change la logique, on augmente ce numero : les vieux caches sont alors ignores.
CACHE_VERSION = 5
REQUIRED_KEYS = {"version", "method", "topics", "sections"}


def decouper_en_tranches(texte):
    mots = texte.split()
    if not mots:
        return []


    nb_tranches = max(MIN_TRANCHES, len(mots) // TAILLE_TRANCHE)
    taille = ceil(len(mots) / nb_tranches)

    tranches = []
    for debut in range(0, len(mots), taille):
        tranche = " ".join(mots[debut:debut + taille])
        tranches.append(tranche)
    return tranches


def mots_les_plus_forts(poids, mots):
    total = poids.sum()

    # argsort() trie les positions du plus PETIT au plus grand poids ;
    # [::-1] inverse la liste pour avoir le plus GRAND en premier.
    positions_triees = poids.argsort()[::-1]

    resultat = []
    for position in positions_triees[:MOTS_PAR_THEME]:
        if poids[position] <= 0:
            continue  # un poids nul ne represente pas le theme
        # On divise par le total pour que le score soit une part facile a lire.
        score = float(poids[position] / total) if total else 0.0
        resultat.append({"word": mots[position], "score": score})
    return resultat


def resultat_vide():
    return {
        "version": CACHE_VERSION,
        "method": "nmf_tfidf",
        "topics": [],
        "sections": [],
    }


def trouver_themes(texte):
    tranches = decouper_en_tranches(texte)
    if not tranches:
        return resultat_vide()

    # 1) Transformer le texte en chiffres (TF-IDF).
    #    Chaque tranche devient une ligne de nombres ; un mot a un score eleve
    #    s'il est frequent dans cette tranche mais rare dans les autres.
    vectoriseur = vectorize(stop_words="english", max_df=MAX_RATIO)
    matrice = vectoriseur.fit_transform(tranches)
    mots = vectoriseur.get_feature_names_out()

    # 2) NMF : regrouper les mots qui apparaissent souvent ensemble en themes.
    #    On ne peut pas demander plus de themes que de tranches ou de mots.
    nb_themes = min(NB_THEMES, matrice.shape[0], matrice.shape[1])
    modele = NMF(
        n_components=nb_themes,
        init="nndsvda",
        random_state=42,   # resultat toujours identique (stable et reproductible)
        max_iter=600,
    )
    poids_tranches = modele.fit_transform(matrice)

    # 3) Pour chaque theme, ses mots les plus representatifs.
    themes = []
    for numero, poids_du_theme in enumerate(modele.components_):
        mots_du_theme = mots_les_plus_forts(poids_du_theme, mots)
        label = " / ".join(m["word"] for m in mots_du_theme[:3])
        themes.append({
            "topic": numero + 1,
            "label": label,
            "words": mots_du_theme,
        })

    # 4) Pour chaque tranche, quel theme domine.
    sections = []
    for numero, poids in enumerate(poids_tranches):
        total = poids.sum()
        repartition = []
        for index_theme, valeur in enumerate(poids):
            part = float(valeur / total) if total else 0.0
            repartition.append({"topic": index_theme + 1, "score": part})

        theme_dominant = int(poids.argmax()) + 1 if len(poids) else 1
        sections.append({
            "section": numero + 1,
            "token_count": len(tranches[numero].split()),
            "dominant_topic": theme_dominant,
            "topic_distribution": repartition,
        })

    return {
        "version": CACHE_VERSION,
        "method": "nmf_tfidf",
        "topics": themes,
        "sections": sections,
    }


def run(book_id):
    """Point d'entree : renvoie les themes du livre (depuis le cache si possible)."""
    path = cache_path(book_id, "topics")

    # Deja calcule ? on renvoie le resultat sauvegarde.
    cached = load_json(path, REQUIRED_KEYS)
    if cached is not None:
        return cached

    # Sinon : on recupere le texte, on simplifie les mots, on calcule, on sauve.
    texte = get_text(book_id)
    texte_simplifie = lemmatize(texte)
    resultat = trouver_themes(texte_simplifie)
    save_json(path, resultat)
    return resultat
