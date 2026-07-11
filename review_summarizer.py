"""Review Summarizer — IA de résumé thématique des avis clients.

Pour chaque restaurant, fetch les avis via les clients API existants
(Yelp + Google), puis produit un résumé structuré par thème :

    🍽️ Cuisine     : positif (4.5/5) — "pâtes fraîches", "sushis ultra-frais"
    🤵 Service      : mitigé (3.2/5) — "accueil chaleureux" vs "service lent"
    🎨 Cadre        : positif (4.1/5) — "ambiance cosy", "terrasse agréable"
    💰 Prix         : négatif (2.8/5) — "trop cher", "addition salée"
    ✨ Global       : 4.2/5 — recommandé

Approche :
- Catégorisation par mots-clés thématiques (FR + EN)
- Sentiment par thème via sentiment.py (lexique local)
- Extraction de snippets représentatifs (top 2 par thème)
- Output en puces markdown

Si ANTHROPIC_API_KEY présente → appelle Claude API pour résumé plus naturel
en plus du résumé structuré.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any

from sentiment import analyze_review


# ── Thèmes et leurs mots-clés (FR + EN) ──
THEMES: dict[str, list[str]] = {
    "Cuisine": [
        "cuisine", "plat", "plats", "nourriture", "food", "manger", "repas",
        "goût", "gout", "saveur", "saveurs", "flaveur", "délicieux", "savoureux",
        "pâtes", "pates", "pasta", "sushi", "sashimi", "pizza", "burger", "viande",
        "poisson", "fruits de mer", "sauce", "dessert", "entrée", "entree",
        "appetizer", "main", "dish", "flavor", "taste", "delicious", "fresh",
        "cooked", "crispy", "tender", "délicat", "raffiné", "frais", "chaud",
        "froid", "brûlé", "brule", "cuit", "recuit", "fade", "insipide",
    ],
    "Service": [
        "service", "serveur", "serveurs", "serveuse", "serveuses", "accueil",
        "accueillant", "accueil", "attente", "poli", "impoli", "aimable",
        "amable", "professionnel", "rapide", "lent", "interminable", "inattentif",
        "staff", "waiter", "waitress", "friendly", "rude", "slow", "fast",
        "attentive", "smile", "sourire", "regarder", "ignorer", "temps d'attente",
    ],
    "Cadre": [
        "cadre", "ambiance", "décor", "decore", "decor", "atmosphère", "atmosphere",
        "cosy", "chaleureux", "chaleureuse", "intime", "romantique", "bruyant",
        "bruissant", "tapageur", "lumière", "lumiere", "lumieres", "musique",
        "terrasse", "salle", "table", "tables", "espace", "étroit", "etroit",
        "spacieux", "confort", "comfortable", "cozy", "loud", "noisy", "quiet",
        "romantic", "intimate", "atmosphere", "vibe", "charming", "charm",
    ],
    "Prix": [
        "prix", "price", "cher", "chère", "chere", "chères", "cheres", "pas cher",
        "bon marché", "bon marche", "économique", "abordable", "raisonnable",
        "exagéré", "exagere", "hors de prix", "addition", "note", "carte",
        "menu", "formule", "déjeuner", "dejeuner", "expensive", "cheap", "affordable",
        "pricey", "value", "rapport qualité-prix", "worth", "bill", "check",
        "budget", "wallet", "portefeuille", "prix correct", "trop cher",
    ],
    "Propreté": [
        "propre", "propreté", "proprete", "sale", "malpropre", "hygiène",
        "hygiene", "clean", "dirty", "sanitary", "crumbs", "table sale",
    ],
}


@dataclass
class ThemeSummary:
    theme: str
    avg_rating: float          # moyenne des ratings des avis qui parlent de ce thème
    sentiment_label: str       # Positif / Négatif / Neutre / Mixte
    sentiment_score: float     # [-1, +1]
    snippets: list[str]        # extraits représentatifs (max 2)
    hit_count: int             # nb d'avis qui match ce thème

    def badge_emoji(self) -> str:
        return {"Positif": "😊", "Négatif": "😡", "Neutre": "😐", "Mixte": "🤔"}.get(self.sentiment_label, "😐")


@dataclass
class ReviewSummary:
    global_rating: float       # moyenne tous avis
    themes: list[ThemeSummary]
    recommendation: str        # "Recommandé" / "Mitigé" / "Déconseillé"
    prose: str | None = None   # résumé LLM si ANTHROPIC_API_KEY dispo
    source: str = "local"      # "local" | "claude-api"
    review_count: int = 0


def _classify_review(text: str) -> list[str]:
    """Retourne la liste des thèmes abordés dans l'avis."""
    low = text.lower()
    matched = []
    for theme, kws in THEMES.items():
        if any(kw in low for kw in kws):
            matched.append(theme)
    return matched or ["Global"]


def _extract_snippet(text: str, theme: str, max_chars: int = 140) -> str:
    """Extrait un court snippet autour d'un mot-clé du thème."""
    low = text.lower()
    kws = THEMES.get(theme, [])
    for kw in kws:
        idx = low.find(kw)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(kw) + 80)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(text):
                snippet = snippet + "…"
            return snippet[:max_chars]
    # Pas de mot-clé trouvé → début du texte
    return text[:max_chars].strip() + ("…" if len(text) > max_chars else "")


def _fetch_reviews(restaurant: dict, yelp_client=None, google_client=None) -> list[dict]:
    """Récupère les avis depuis les sources disponibles.

    Le dict merger contient `source` (primaire) et `id` (l'ID dans cette source).
    On utilise cette paire pour fetch, comme le fait app.py pour le bouton "Avis".
    """
    reviews: list[dict] = []
    primary_source = restaurant.get("source")
    primary_id = restaurant.get("id")
    sources = restaurant.get("sources", [primary_source] if primary_source else [])

    # Yelp
    if yelp_client and yelp_client.available and "yelp" in sources and primary_id:
        if primary_source == "yelp":
            revs, err = yelp_client.get_reviews(primary_id)
        else:
            # ID d'une autre source — pas cross-référencé, skip
            revs, err = [], None
        if not err and revs:
            for r in revs:
                text = r.get("text", "")
                if not text and isinstance(r.get("text"), dict):
                    text = " ".join(r["text"].get("text", ""))
                reviews.append({"text": text, "rating": r.get("rating", 0)})

    # Google
    if google_client and google_client.available and "google" in sources and primary_id:
        if primary_source == "google":
            revs, err = google_client.get_reviews(primary_id)
        else:
            revs, err = [], None
        if not err and revs:
            for r in revs:
                reviews.append({"text": r.get("text", ""), "rating": r.get("rating", 0)})

    return reviews


def summarize_reviews(
    reviews: list[dict],
    restaurant: dict | None = None,
    use_claude: bool | None = None,
) -> ReviewSummary:
    """Résumé thématique d'une liste d'avis.

    reviews : list de {"text": str, "rating": float}
    restaurant : dict optionnel pour contexte (nom, note globale)
    use_claude : si True, tente Claude API. None → auto-detect ANTHROPIC_API_KEY
    """
    if not reviews:
        return ReviewSummary(
            global_rating=0.0,
            themes=[],
            recommendation="Aucun avis disponible",
            review_count=0,
        )

    # Notes globales
    ratings = [r.get("rating", 0) for r in reviews if r.get("rating")]
    global_rating = sum(ratings) / len(ratings) if ratings else 0.0

    # Catégorisation
    theme_buckets: dict[str, list[dict]] = {t: [] for t in THEMES}
    theme_buckets["Global"] = []
    for r in reviews:
        text = r.get("text", "")
        if not text:
            continue
        matched = _classify_review(text)
        for t in matched:
            theme_buckets[t].append(r)
        theme_buckets["Global"].append(r)

    # Score par thème
    themes: list[ThemeSummary] = []
    for theme_name in ["Cuisine", "Service", "Cadre", "Prix", "Propreté"]:
        bucket = theme_buckets.get(theme_name, [])
        if not bucket:
            continue
        # Sentiment agrégé
        scores = []
        labels_count = {"Positif": 0, "Négatif": 0, "Neutre": 0, "Mixte": 0}
        for r in bucket:
            sr = analyze_review(r.get("text", ""))
            scores.append(sr.score)
            labels_count[sr.label] = labels_count.get(sr.label, 0) + 1
        avg_sent = sum(scores) / len(scores) if scores else 0.0
        # Label dominant
        label = max(labels_count, key=labels_count.get)
        # Rating moyen
        t_ratings = [r.get("rating", 0) for r in bucket if r.get("rating")]
        avg_r = sum(t_ratings) / len(t_ratings) if t_ratings else 0.0
        # Ajustement : si label Négatif mais avg_r >= 4, passe en Mixte
        if label == "Négatif" and avg_r >= 4.0:
            label = "Mixte"
        elif label == "Positif" and avg_r <= 2.5:
            label = "Mixte"
        # Snippets : 2 meilleurs (positifs) ou 2 pires (négatifs)
        sorted_bucket = sorted(bucket, key=lambda r: abs(analyze_review(r.get("text", "")).score), reverse=True)
        snippets = [_extract_snippet(r.get("text", ""), theme_name) for r in sorted_bucket[:2]]

        themes.append(ThemeSummary(
            theme=theme_name,
            avg_rating=round(avg_r, 2),
            sentiment_label=label,
            sentiment_score=round(avg_sent, 3),
            snippets=snippets,
            hit_count=len(bucket),
        ))

    # Recommandation basée sur note globale + sentiment moyen
    avg_sent = sum(t.sentiment_score for t in themes) / len(themes) if themes else 0.0
    if global_rating >= 4.0 and avg_sent >= 0.15:
        recommendation = "Recommandé"
    elif global_rating <= 2.5 or avg_sent <= -0.3:
        recommendation = "Déconseillé"
    else:
        recommendation = "Mitigé"

    # Prose LLM optionnel
    prose = None
    source = "local"
    claude_enabled = use_claude if use_claude is not None else bool(os.getenv("ANTHROPIC_API_KEY"))
    if claude_enabled:
        try:
            prose = _claude_summary(reviews, restaurant, themes)
            if prose:
                source = "claude-api"
        except Exception:
            prose = None

    return ReviewSummary(
        global_rating=round(global_rating, 2),
        themes=themes,
        recommendation=recommendation,
        prose=prose,
        source=source,
        review_count=len(reviews),
    )


def _claude_summary(reviews: list[dict], restaurant: dict | None, themes: list[ThemeSummary]) -> str | None:
    """Appelle Claude API pour un résumé naturel en français."""
    try:
        import requests
        key = os.getenv("ANTHROPIC_API_KEY") or _get_anthropic_secret()
        if not key:
            return None
        name = restaurant.get("name", "ce restaurant") if restaurant else "ce restaurant"
        revs_text = "\n".join(
            f"- ({r.get('rating', '?')}★) {r.get('text', '')[:280]}"
            for r in reviews[:10]
        )
        themes_text = "\n".join(
            f"- {t.theme}: {t.sentiment_label} ({t.sentiment_score:+.2f})"
            for t in themes
        )
        system = (
            "Tu es Emma, une critique gastronomique IA. Résume les avis clients en français, "
            "en 4-5 phrases maximum, style journalistique chaleureux. "
            "Mentionne les points forts et faibles principaux. Pas d'émojis dans le corps."
        )
        user = (
            f"Restaurant : {name}\n"
            f"Thèmes détectés :\n{themes_text}\n\n"
            f"Avis ({len(reviews)}) :\n{revs_text}\n\n"
            f"Rédige un résumé naturel."
        )
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=15,
        )
        r.raise_for_status()
        parts = [b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text"]
        return "".join(parts).strip() or None
    except Exception:
        return None


def _get_anthropic_secret() -> str:
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return ""


def render_summary_markdown(summary: ReviewSummary) -> str:
    """Rendu HTML/markdown du résumé pour affichage dans Streamlit."""
    if not summary.themes and summary.review_count == 0:
        return '<p style="color:#888;font-style:italic;">Aucun avis à analyser.</p>'

    emoji_map = {"Cuisine": "🍽️", "Service": "🤵", "Cadre": "🎨", "Prix": "💰", "Propreté": "🧼", "Global": "✨"}
    parts = [f'<div style="background:#fce4ec;padding:12px;border-radius:10px;">']
    parts.append(
        f'<div style="font-weight:700;color:#880e4f;margin-bottom:8px;">'
        f'Résumé IA — {summary.review_count} avis — note globale {summary.global_rating:.1f}/5 — '
        f'<span style="color:#ad1457;">{summary.recommendation}</span>'
        f'</div>'
    )
    for t in summary.themes:
        e = emoji_map.get(t.theme, "•")
        parts.append(
            f'<div style="margin-bottom:6px;">'
            f'<strong>{e} {t.theme}</strong> — {t.sentiment_label} {t.badge_emoji()} '
            f'({t.sentiment_score:+.2f}, {t.hit_count} avis)'
            f'</div>'
        )
        for snip in t.snippets:
            parts.append(f'<div style="font-size:0.8rem;color:#666;margin-left:20px;font-style:italic;">"{snip}"</div>')
    if summary.prose:
        parts.append(f'<div style="margin-top:10px;padding:10px;background:white;border-radius:6px;font-size:0.88rem;">{summary.prose}</div>')
    parts.append(f'<div style="font-size:0.7rem;color:#999;margin-top:8px;">source: {summary.source}</div>')
    parts.append('</div>')
    return "".join(parts)


def summarize_for_restaurant(
    restaurant: dict,
    yelp_client=None,
    google_client=None,
    use_claude: bool | None = None,
) -> ReviewSummary:
    """Point d'entrée complet : fetch + summarize. Utilisable directement dans app.py."""
    reviews = _fetch_reviews(restaurant, yelp_client, google_client)
    return summarize_reviews(reviews, restaurant=restaurant, use_claude=use_claude)


# ── Tests inline ──
if __name__ == "__main__":
    fake_reviews = [
        {"text": "Cuisine délicieuse, pâtes fraîches incroyables. Service un peu lent par contre.", "rating": 4},
        {"text": "Cadre romantique super cosy, parfait pour un dîner. Pizza au top.", "rating": 5},
        {"text": "Très bon accueil, serveurs aimables. Par contre c'est beaucoup trop cher pour ce que c'est.", "rating": 3},
        {"text": "Pas terrible : plats froids et addition salée. Service impoli.", "rating": 2},
        {"text": "Endroit charmant, terrasse agréable, bonne adresse.", "rating": 4},
    ]
    s = summarize_reviews(fake_reviews, restaurant={"name": "Pizzeria Popolare"})
    print(f"Note globale: {s.global_rating}/5 — {s.recommendation}\n")
    for t in s.themes:
        print(f"  {t.theme}: {t.sentiment_label} {t.badge_emoji()} (score={t.sentiment_score:+.2f}, hits={t.hit_count}, rating={t.avg_rating})")
        for sn in t.snippets:
            print(f"    → {sn!r}")
