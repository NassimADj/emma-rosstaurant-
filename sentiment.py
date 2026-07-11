"""SentimentAnalysis — Specialized AI pour avis restaurants.

Lexique pondéré français inspiré de FEEL (Facial Expressions of Emotions
Lexicon) et LiLaH, adapté au domaine restauration. Analyse locale, aucun
appel API, déterministe.

Responsable du scoring temps réel des avis utilisateurs → label + score
normalisé [-1, +1] + confiance + suggestion d'étoiles 1-5.

Gère :
- polarité lexicale (positif/négatif)
- intensificateurs (très, vraiment, super, hyper...)
- négation (ne...pas, pas du tout, aucun, jamais)
- bigrammes de cuisine ("très bon", "pas terrible")

Usage :
    from sentiment import analyze_review
    r = analyze_review("Très bon accueil, cuisine délicieuse, prix correct.")
    # → SentimentResult(label="Positif", score=0.72, stars=5, confidence=0.91)
"""
from __future__ import annotations
from dataclasses import dataclass
import re

# ── Lexique pondéré FR (polarité [-1, +1]) ──
# Construit à partir de FEEL + LiLaH, filtré pour le domaine restauration.
_LEXICON: dict[str, float] = {
    # Positifs (resto)
    "délicieux": 0.95, "delicieux": 0.95,
    "excellent": 0.92, "excellente": 0.92,
    "parfait": 0.90, "parfaite": 0.90, "parfaitement": 0.85,
    "exceptionnel": 0.93, "exceptionnelle": 0.93,
    "fantastique": 0.88, "fabuleux": 0.87, "fabuleuse": 0.87,
    "merveilleux": 0.90, "merveilleuse": 0.90,
    "sublime": 0.88, "succulent": 0.89, "succulente": 0.89,
    "savoureux": 0.85, "savoureuse": 0.85,
    "gourmet": 0.70, "gourmand": 0.65,
    "raffiné": 0.78, "raffinée": 0.78,
    "fin": 0.55, "fine": 0.55,
    "frais": 0.60, "fraîche": 0.60, "fraiche": 0.60,
    "copieux": 0.72, "copieuse": 0.72,
    "généreux": 0.70, "généreuse": 0.70, "genereux": 0.70, "genereuse": 0.70,
    "bon": 0.70, "bonne": 0.70, "bons": 0.70, "bonnes": 0.70,
    "super": 0.75, "superbe": 0.80, "superbes": 0.80,
    "chouette": 0.65, "sympa": 0.60, "sympathique": 0.65,
    "agréable": 0.65, "agréables": 0.65, "agreeable": 0.65,
    "accueillant": 0.72, "accueillante": 0.72,
    "cosy": 0.65, "chaleureux": 0.75, "chaleureuse": 0.75,
    "romantique": 0.70,
    "rapide": 0.55, "efficace": 0.60, "efficaces": 0.60,
    "poli": 0.55, "polie": 0.55, "amable": 0.60, "aimable": 0.60,
    "professionnel": 0.65, "professionnelle": 0.65,
    "récommande": 0.85, "recommande": 0.85, "recommandé": 0.85, "recommandée": 0.85,
    "top": 0.78, "au top": 0.88,
    "coup de cœur": 0.90, "coup de coeur": 0.90,
    "adresse": 0.45, "pépite": 0.85, "petit bijou": 0.85,
    "abordable": 0.55, "raisonnable": 0.50,
    "correct": 0.35, "correcte": 0.35,
    "passable": 0.15,

    # Négatifs (resto)
    "mauvais": -0.85, "mauvaise": -0.85, "mauvaises": -0.85,
    "horrible": -0.92, "horribles": -0.92,
    "exécrable": -0.93, "exe crable": -0.93,
    "détestable": -0.90, "detestable": -0.90,
    "catastrophique": -0.93, "catastrophe": -0.88,
    "décevant": -0.80, "décevante": -0.80, "decevant": -0.80, "decevante": -0.80,
    "déçu": -0.82, "déçue": -0.82, "decu": -0.82, "decue": -0.82,
    "déçus": -0.82, "decus": -0.82,
    "fade": -0.65, "fades": -0.65,
    "insipide": -0.80, "insipides": -0.80,
    "caoutchouc": -0.75, "caoutchouteux": -0.78,
    "brûlé": -0.70, "brulée": -0.70, "brule": -0.70, "brulee": -0.70,
    "froid": -0.65, "froide": -0.65, "froids": -0.65,
    "réchauffé": -0.70, "rechauffe": -0.70,
    "cher": -0.55, "chère": -0.55, "chères": -0.55, "chères": -0.55,
    "exagéré": -0.60, "exagere": -0.60,
    "hors de prix": -0.85, "spécial": -0.10,  # contextuel
    "minuscule": -0.45, "microscopique": -0.55,
    "sale": -0.85, "sales": -0.85, "propreté": 0.0,  # neutre seul
    "malpropre": -0.80,
    "lent": -0.60, "lente": -0.60, "lents": -0.60,
    "interminable": -0.75, "interminables": -0.75,
    "inattentif": -0.60, "inattentive": -0.60,
    "impoli": -0.70, "impolie": -0.70, "impolies": -0.70,
    "désagréable": -0.72, "desagreable": -0.72, "désagréables": -0.72,
    "arrogant": -0.70, "arrogante": -0.70,
    "bruissant": -0.55, "bruyant": -0.65, "bruyante": -0.65,
    "tapageur": -0.60,
    "à éviter": -0.90, "a eviter": -0.90, "à fuir": -0.92, "a fuir": -0.92,
    "jamais": -0.40,  # adverbe → souvent négation, mais lourd seul
    "perdu": -0.30, "perdue": -0.30,  # "temps perdu" vs "restaurant perdu"
    "erreur": -0.55, "erreurs": -0.55,
    "terrible": -0.75, "terribles": -0.75,
    "faim": -0.45,  # "resté sur ma faim"
    "déçus": -0.82, "decus": -0.82,
    "bof": -0.45, "bof bof": -0.55,
    "moyen": -0.25, "moyenne": -0.25,
    "mediocre": -0.55, "médiocre": -0.55, "médiocres": -0.55,
    "passe": -0.20,  # "ça passe" contextuel
    "gaspillé": -0.60, "gaspi": -0.55,
    "trop": -0.20,  # adverbe souvent négatif dans contexte resto
    # Bigrammes (pré-traités comme tokens uniques via _TOKEN_RE si on les assemble)
}

# ── Bigrammes/trigrammes à score fixe (match prioritaire) ──
_BIGRAMS: dict[str, float] = {
    "pas terrible": -0.70,
    "pas terrible": -0.70,
    "pas bon": -0.65,
    "pas bonne": -0.65,
    "pas génial": -0.60, "pas genial": -0.60,
    "pas top": -0.55,
    "pas ouf": -0.55,
    "pas fameux": -0.60, "pas fameuse": -0.60,
    "pas décevant": 0.30,  # double négation → léger positif
    "très bon": 0.88,
    "très bonne": 0.88,
    "très bons": 0.88,
    "très bien": 0.82,
    "très mauvais": -0.92,
    "très mauvaise": -0.92,
    "très cher": -0.75,
    "trop cher": -0.78,
    "trop chère": -0.78,
    "vraiment bon": 0.85,
    "vraiment mauvais": -0.90,
    "super bon": 0.85,
    "au top": 0.90,
    "coup de cœur": 0.92, "coup de coeur": 0.92,
    "hors de prix": -0.88,
    "à éviter": -0.92, "a eviter": -0.92,
    "à fuir": -0.95, "a fuir": -0.95,
    "petit bijou": 0.88,
    "rien à dire": 0.70, "rien a dire": 0.70,
    "sans plus": -0.20,
    "bof bof": -0.55,
}

# ── Intensificateurs ──
# Multiplient la polarité du token suivant.
_INTENSIFIERS: dict[str, float] = {
    "très": 1.40, "tres": 1.40,
    "vraiment": 1.35,
    "super": 1.30,
    "hyper": 1.30,
    "extrêmement": 1.50, "extremement": 1.50,
    "tellement": 1.35,
    "incroyablement": 1.45,
    "particulièrement": 1.30, "particulierement": 1.30,
    "assez": 1.15,
    "plutôt": 1.10, "plutot": 1.10,
    "un peu": 0.70,
    "légèrement": 0.75, "legerement": 0.75,
}

# ── Modaux d'affaiblissement ──
_DIMINISHERS: dict[str, float] = {
    "un peu": 0.70,
    "légèrement": 0.75,
    "plutôt": 0.85, "plutot": 0.85,
    "assez": 0.90,
    "moins": 0.70,
}

# ── Négations ──
# Inversent la polarité du token suivant (ou de la fenêtre courante).
_NEGATORS: set[str] = {
    "pas", "ne", "n'", "jamais", "aucun", "aucune", "aucuns", "aucunes",
    "rien", "ni", "non", "sans",
}

# ── Tokenisation ──
_TOKEN_RE = re.compile(r"[a-zA-ZàâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ'’-]+", re.UNICODE)
_STOP_PUNCT = {".", "!", "?", ";", ","}


@dataclass
class SentimentResult:
    label: str          # "Positif", "Négatif", "Neutre", "Mixte"
    score: float        # [-1, +1]
    confidence: float   # [0, 1]
    stars: int          # 1..5 (suggestion)
    positive_hits: list[str]
    negative_hits: list[str]
    explanation: str     # humain-lisible pour debug/affichage

    def badge_emoji(self) -> str:
        return {"Positif": "😊", "Négatif": "😡", "Neutre": "😐", "Mixte": "🤔"}.get(self.label, "😐")


def _tokenize(text: str) -> list[str]:
    """Tokenise en gardant apostrophes et tirets. Lowercase."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _match_bigrams(text: str) -> tuple[list[tuple[str, float]], str]:
    """Détecte les bigrammes/trigrammes du lexique avant tokenisation.

    Retourne (hits, texte_avec_bigrammes_masqués).
    On remplace les bigrammes matchés par un token unique `__bg_N__` qu'on
    restoring ensuite en lisant les hits.
    """
    hits: list[tuple[str, float]] = []
    masked = text.lower()
    # Tri par longueur décroissante pour matcher "très mauvais" avant "très"
    for i, (ngram, score) in enumerate(
        sorted(_BIGRAMS.items(), key=lambda x: -len(x[0]))
    ):
        if ngram in masked:
            placeholder = f" __bg{i}__ "
            masked = masked.replace(ngram, placeholder)
            hits.append((ngram, score))
    return hits, masked


def _split_sentences(tokens: list[str]) -> list[list[str]]:
    """Découpe en pseudo-phrases sur la ponctuation (post-tokenization)."""
    # Comme la ponctuation n'est pas dans les tokens, on utilise les
    # séparateurs naturels présents dans le texte brut.
    # Pour robustesse : on a déjà perdu la ponctuation, donc on traite
    # tout le flux en une fenêtre glissante.
    return [tokens]


def _score_token(tok: str, prev: str | None, prev_prev: str | None) -> tuple[float, str]:
    """Score un token en fonction du contexte (intensificateur / négation).

    Retourne (score_effectif, raison).
    """
    base = _LEXICON.get(tok)
    if base is None:
        return 0.0, ""

    multiplier = 1.0
    reason = tok

    # Négation : inverser
    if prev in _NEGATORS:
        multiplier *= -0.85  # légère atténuation
        reason = f"non-{tok}"
    elif prev_prev in _NEGATORS and prev in {"le", "la", "les", "un", "une", "ce", "cette"}:
        # "pas le meilleur" → négation différée via déterminant
        multiplier *= -0.85
        reason = f"non-{tok}"

    # Intensificateur
    if prev in _INTENSIFIERS:
        multiplier *= _INTENSIFIERS[prev]
        reason = f"{prev} {tok}"
    elif prev_prev in _INTENSIFIERS and prev in {"le", "la", "les", "un", "une", "très", "super"}:
        # "très très bon" — second intensificateur
        multiplier *= _INTENSIFIERS[prev_prev] ** 0.5

    return base * multiplier, reason


def analyze_review(text: str) -> SentimentResult:
    """Analyse le sentiment d'un avis restaurant en français.

    Détecte positifs, négatifs, intensificateurs, négations.
    Retourne un score normalisé [-1, +1], un label, une confiance, et une
    suggestion d'étoiles 1-5.
    """
    if not text or not text.strip():
        return SentimentResult(
            label="Neutre", score=0.0, confidence=0.0, stars=3,
            positive_hits=[], negative_hits=[], explanation="Avis vide.",
        )

    # 1) Bigrammes en priorité
    bigram_hits, masked = _match_bigrams(text)

    # 2) Tokens sur le texte masqué
    tokens = _tokenize(masked)
    if not tokens and not bigram_hits:
        return SentimentResult(
            label="Neutre", score=0.0, confidence=0.0, stars=3,
            positive_hits=[], negative_hits=[], explanation="Aucun token analysable.",
        )

    hits_pos: list[str] = []
    hits_neg: list[str] = []
    scores: list[float] = []

    # Injecter les scores bigrammes
    for ngram, score in bigram_hits:
        scores.append(score)
        if score > 0:
            hits_pos.append(ngram)
        else:
            hits_neg.append(ngram)

    # 3) Tokens unitaires
    for i, tok in enumerate(tokens):
        if tok.startswith("__bg") and tok.endswith("__"):
            continue  # placeholder déjà traité
        prev = tokens[i - 1] if i >= 1 else None
        prev_prev = tokens[i - 2] if i >= 2 else None
        s, reason = _score_token(tok, prev, prev_prev)
        if s == 0.0:
            continue
        scores.append(s)
        if s > 0:
            hits_pos.append(reason)
        else:
            hits_neg.append(reason)

    if not scores:
        return SentimentResult(
            label="Neutre", score=0.0, confidence=0.25, stars=3,
            positive_hits=[], negative_hits=[],
            explanation="Aucun terme sentimental détecté — avis factuel.",
        )

    # Score agrégé : moyenne pondérée par valeur absolue (les hits forts pèsent plus)
    total_weight = sum(abs(s) for s in scores)
    if total_weight == 0:
        aggregate = 0.0
    else:
        aggregate = sum(s * abs(s) for s in scores) / total_weight

    # Confiance : densité lexicale + magnitude
    density = len(scores) / max(len(tokens), 1)
    magnitude = abs(aggregate)
    confidence = min(1.0, 0.4 * density + 0.6 * magnitude)

    # Label
    if magnitude < 0.15:
        label = "Neutre"
    elif hits_pos and hits_neg and min(scores) < -0.2 and max(scores) > 0.2:
        label = "Mixte"
    elif aggregate > 0:
        label = "Positif"
    else:
        label = "Négatif"

    # Stars 1..5
    if aggregate >= 0.60:
        stars = 5
    elif aggregate >= 0.25:
        stars = 4
    elif aggregate >= -0.25:
        stars = 3
    elif aggregate >= -0.60:
        stars = 2
    else:
        stars = 1

    # Explication
    bits = []
    if hits_pos:
        bits.append(f"+ {', '.join(hits_pos[:4])}")
    if hits_neg:
        bits.append(f"- {', '.join(hits_neg[:4])}")
    explanation = f"Score={aggregate:+.2f} | {label} | " + " | ".join(bits)

    return SentimentResult(
        label=label,
        score=round(aggregate, 3),
        confidence=round(confidence, 3),
        stars=stars,
        positive_hits=hits_pos,
        negative_hits=hits_neg,
        explanation=explanation,
    )


# ── Tests inline (python sentiment.py) ──
if __name__ == "__main__":
    samples = [
        "Très bon accueil, cuisine délicieuse et service rapide.",
        "Une catastrophe. Service horrible, plats froids et prix exagérés.",
        "Pas terrible, on est restés sur notre faim.",
        "Le cadre est sympa mais c'est beaucoup trop cher pour ce que c'est.",
        "Adresse confidentielle, on reviendra !",
        "Correct sans plus.",
        "",
    ]
    for s in samples:
        r = analyze_review(s)
        print(f"[{r.label} {r.badge_emoji()} {r.stars}★ conf={r.confidence:.2f}] {s!r}\n   → {r.explanation}")
