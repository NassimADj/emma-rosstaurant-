"""Emma AI Concierge — Content AI : moteur de recommandation conversationnel.

L'utilisateur tape une demande en langage naturel FR :
    « Je veux un resto italien romantique à Paris »
    « Un truc pas cher dans le 11e »
    « Sushi pour deux ce soir »

Le module :
1. Parse la demande → critères (catégorie, arrondissement, prix, ambiance, mots-clés)
2. Si une liste de restaurants déjà chargée est fournie → filtre + ranking local
3. Sinon → déclenche une recherche via les clients API existants
4. Rédige une réponse prose « style IA » : phrase d'accroche + reco + justification
5. Si ANTHROPIC_API_KEY présent → utilise Claude API pour génération plus naturelle

Pas de dépendance dure sur Claude : fallback deterministe si clé absente.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Any

from config import CATEGORIES, PARIS_ARRONDISSEMENTS, PRICE_LABELS, score_pertinent


# ── Vocabulaire d'ambiance (pas dans config.py car propre au concierge) ──
AMBIENCE_KEYWORDS: dict[str, list[str]] = {
    "romantique": ["romantique", "romantiques", "amoureux", "en amoureux", "rendez-vous", "date", "chic"],
    "cosy": ["cosy", "chaleureux", "chaleureuse", "intime", "intime"],
    "affaires": ["affaires", "business", "pro", "professionnel", "déjeuner d'affaires"],
    "famille": ["famille", "familial", "enfants", "enfant"],
    "vegan": ["vegan", "végétarien", "vegetarien", "végé", "vege"],
    "pas cher": ["pas cher", "pas chère", "bon marché", "économique", "budget", "étudiant", "étudiant"],
    "gastronomique": ["gastronomique", "étoilé", "etoile", "michelin", "fine dining", "raffiné"],
    "terrasse": ["terrasse", "en extérieur", "plein air"],
    "brunch": ["brunch", "petit-déjeuner", "petit dejeuner", "matin"],
    "tapas": ["tapas", "apéro", "apero", "à partager"],
    "halal": ["halal", "casher", "kasher"],
}


# ── Patterns de parsing ──
_ARR_RE = re.compile(r"\b(\d{1,2})(?:\s*(?:er|ème|eme|e|th))?\b(?:\s*arr)?", re.IGNORECASE)
_PRICE_RE = re.compile(r"\b(€{1,4}|e{1,4}|pas cher|bon marché|économique|luxe| gastronomique)\b", re.IGNORECASE)


@dataclass
class ConciergeQuery:
    raw: str
    category: str | None = None       # label FR (ex: "Italien")
    category_slug: str | None = None  # slug API (ex: "italian")
    arrondissement: str | None = None  # label FR (ex: "11e")
    arrondissement_code: str | None = None  # code postal (ex: "75011")
    price: int | None = None          # 1..4
    ambience: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def summary(self) -> str:
        bits = []
        if self.category:
            bits.append(f"cat={self.category}")
        if self.arrondissement:
            bits.append(f"arr={self.arrondissement}")
        if self.price:
            bits.append(f"prix={PRICE_LABELS.get(self.price, '?')}")
        if self.ambience:
            bits.append(f"ambiance={','.join(self.ambience)}")
        return " | ".join(bits) if bits else "aucun critère extrait"


@dataclass
class ConciergeReply:
    text: str                # réponse prose pour l'utilisateur
    query: ConciergeQuery     # critères extraits (debug/affichage)
    restaurants: list[dict]  # restaurants sélectionnés (top 3 max)
    source: str              # "claude-api" | "local-template"


def parse_query(text: str) -> ConciergeQuery:
    """Extrait critères structurés depuis une phrase en langage naturel FR."""
    q = ConciergeQuery(raw=text)
    low = text.lower()

    # Catégorie : match sur labels ou synonyms
    for label, slug in CATEGORIES.items():
        if slug is None:
            continue
        if label.lower() in low:
            q.category = label
            q.category_slug = slug
            break

    # Synonymes catégories (mots courants pas dans CATEGORIES)
    syn = {
        "jap": "japanese", "japonais": "japanese",
        "resto japonais": "japanese",
        "pâtes": "italian", "pates": "italian", "pasta": "italian",
        "tacos": "mexican", "tex-mex": "mexican",
        "bibim": "korean", "coréen": "korean",
        "cantonais": "chinese", "asiatique": "chinese",
        "kebab": "lebanese", "chawarma": "lebanese", "shawarma": "lebanese",
        "mezze": "lebanese",
        "paella": "spanish", "tapas": "spanish",
        "pad thai": "thai", "thaï": "thai", "thai": "thai",
        "burrata": "italian",
        "burger": "burgers",
        "pizza": "pizza", "pizzeria": "pizza", "pizz": "pizza",
        "sushi": "sushi", "sushis": "sushi",
        "brasserie": "brasseries",
        "bistrot": "bistros", "bistro": "bistros",
        "crêperie": "creperies", "creperie": "creperies",
        "glace": "icecream", "glaces": "icecream", "glacier": "icecream",
        "veggie": "vegan", "végé": "vegan", "vege": "vegan",
        "chinois": "chinese",
        "indien": "indian", "curry": "indian",
        "libanais": "lebanese",
        "grec": "greek", "grècque": "greek", "grecque": "greek",
        "espagnol": "spanish",
        "coréen": "korean", "coreen": "korean",
        "vietnamien": "vietnamese", "pho": "vietnamese",
        "fruit de mer": "seafood", "fruits de mer": "seafood",
    }
    if q.category is None:
        for k, slug in syn.items():
            if k in low:
                q.category_slug = slug
                # reversed lookup label
                for lbl, sl in CATEGORIES.items():
                    if sl == slug:
                        q.category = lbl
                        break
                break

    # Arrondissement
    m = _ARR_RE.search(text)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 20:
            label = f"{n}e" if n != 1 else "1er"
            q.arrondissement = label
            q.arrondissement_code = PARIS_ARRONDISSEMENTS.get(label)

    # Prix
    pm = _PRICE_RE.search(text)
    if pm:
        tok = pm.group(1).lower()
        if "pas cher" in tok or "bon marché" in tok or "économique" in tok:
            q.price = 1
        elif "gastronomique" in tok or "luxe" in tok:
            q.price = 4
        else:
            q.price = min(4, max(1, len(tok.replace("e", "").replace("€", "")) or 1))

    # Ambiance
    for amb, kws in AMBIENCE_KEYWORDS.items():
        if any(k in low for k in kws):
            q.ambience.append(amb)

    # Mots-clés résiduels (hors stopwords)
    stopwords = {"je", "veux", "voudrais", "cherche", "un", "une", "des", "le", "la", "les",
                 "pour", "ce", "soir", "midi", "aller", "avec", "dans", "à", "a", "paris",
                 "resto", "restaurant", "bon", "bons", "petit", "gros", "truc", "chose"}
    tokens = [t for t in re.findall(r"[a-zàâäéèêëîïôöùûüç]+", low) if t not in stopwords]
    q.keywords = tokens[:6]

    return q


def _filter_restaurants(restos: list[dict], q: ConciergeQuery) -> list[dict]:
    """Filtre une liste de restaurants (format merger) selon critères."""
    out = []
    for r in restos:
        # Catégorie
        if q.category_slug:
            cats = [c.lower() for c in r.get("categories", [])]
            # Slug peut être dans alias
            if q.category_slug not in cats and not any(q.category_slug in c for c in cats):
                # tentative sur alias FR
                if q.category and q.category.lower() not in " ".join(cats).lower():
                    continue
        # Arrondissement (code postal dans adresse)
        if q.arrondissement_code:
            addr = " ".join(r.get("location", {}).get("display_address", [])).replace(" ", "")
            if q.arrondissement_code not in addr:
                continue
        # Prix
        if q.price:
            if r.get("price_level") and r["price_level"] != q.price:
                continue
        out.append(r)
    return out


def _rank(restos: list[dict], q: ConciergeQuery) -> list[dict]:
    """Score = score_pertinent + bonus mots-clés nom + bonus ambiance."""
    scored = []
    for r in restos:
        base = score_pertinent(r.get("rating", 3.5), r.get("review_count", 0))
        name_low = r.get("name", "").lower()
        bonus = 0.0
        for kw in q.keywords:
            if kw in name_low:
                bonus += 0.15
        # Ambiance : on ne peut pas vraiment savoir sans reviews, on bonus les reviews count
        if q.ambience:
            bonus += min(0.3, r.get("review_count", 0) / 500)
        scored.append((base + bonus, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:3]]


# ── Templates prose fallback (pas de Claude API) ──
_TEMPLATES = {
    "intro": [
        "Parfait, j'ai trouvé une adresse qui devrait vous convenir",
        "Excellente idée — voici ma recommandation",
        "D'après ce que vous cherchez, je vous propose",
        "Mon radar restos a déclenché sur cette adresse",
    ],
    "justif_cat": {
        "Italien": "une cuisine italienne authentique avec des pâtes fraîches et une ambiance chaleureuse",
        "Japonais": "un sushitrakus de qualité avec du poisson ultra-frais",
        "Français": "une table française de tradition, bistrot de quartier soigné",
        "Chinois": "une adresse chinoise maîtrisée, wok et vapeur au rendez-vous",
        "Thaï": "une cuisine thaï équilibrée entre sucré, salé, acide et piquant",
        "Indien": "des épices maîtrisées et des currys parfumés",
        "Mexicain": "tacos et guacamole qui envoient du piquant",
        "Libanais": "des mezze à partager, falafels croustillants et houmous onctueux",
        "Coréen": "bibimbap et barbecue coréen dans une ambiance conviviale",
        "Vietnamien": "pho parfumé et rouleaux de printemps frais",
        "Grec": "une cuisine grecque ensoleillée, tarama et moussaka",
        "Espagnol": "tapas et paella pour un déjeuner ibérique",
        "Créperie": "des crêpes et galettes de sarrasin, beurre salé inclus",
        "Brasserie": "une brasserie parisienne classique, service en blanc et plateaux fruits de mer",
        "Bistro": "un bistro de quartier avec une carte courte qui change au marché",
        "Street Food": "une street food qui décoiffe, rapidité et goût",
        "Sushi": "des sushis travaillés, riz vinaigré parfait",
        "Pizza": "une pizza napolitaine au feu de bois, pâte alvéolée",
        "Burger": "un burger gourmet, viande maturée et bun maison",
        "Vegan": "une table vegan créative, légumes de saison sublimés",
        "Glacier": "un glacier artisanal, sorbets fruits et parfums inventifs",
        "Boulangerie": "une boulangerie de quartier, tourte et viennoiseries au beurre",
        "Fruits de mer": "un plateau fruits de mer frais, huîtres et bulots",
        "Steakhouse": "une viande maturée, grill et sauce maison",
    },
    "justif_amb": {
        "romantique": "cadre romantique parfait pour un dîner à deux",
        "cosy": "ambiance cosy et chaleureuse",
        "affaires": "table adaptée pour un déjeuner d'affaires",
        "famille": "bon pour un repas en famille",
        "vegan": "options végétales soignées",
        "pas cher": "addiction correcte, rapport qualité-prix maîtrisé",
        "gastronomique": "table gastronomique, assiettes raffinées",
        "terrasse": "terrasse agréable dès que le temps le permet",
        "brunch": "brunch le weekend",
        "tapas": "tapas à partager",
        "halal": "options halal disponibles",
    },
}


def _build_local_reply(q: ConciergeQuery, picks: list[dict]) -> str:
    import random
    rng = random.Random(hash(q.raw) & 0xFFFFFFFF)
    intro = rng.choice(_TEMPLATES["intro"])

    if not picks:
        return (
            f"{intro}, mais je n'ai rien trouvé qui matche exactement vos critères "
            f"({q.summary()}). Affinez la recherche dans la barre latérale, "
            "puis relancez-moi avec les nouveaux résultats."
        )

    r = picks[0]
    name = r.get("name", "cette adresse")
    rating = r.get("rating", "?")
    reviews = r.get("review_count", 0)
    addr = ", ".join(r.get("location", {}).get("display_address", [])[:2]) or "Paris"

    # Justification catégorie
    justif_cat = _TEMPLATES["justif_cat"].get(q.category or "", "une table qui devrait plaire")
    # Justification ambiance
    justif_amb = ""
    if q.ambience:
        amb = q.ambience[0]
        justif_amb = " — " + _TEMPLATES["justif_amb"].get(amb, "")

    lignes_alt = ""
    if len(picks) > 1:
        alt = ", ".join(p.get("name", "?") for p in picks[1:3])
        lignes_alt = f"\n\nSi {name} ne vous tente pas, regardez aussi : {alt}."

    return (
        f"{intro} : **{name}** ({rating}★ sur {reviews} avis, {addr}).\n\n"
        f"Pourquoi ce choix : {justif_cat}{justif_amb}. "
        f"J'ai croisé votre demande « {q.raw.strip()} » avec les résultats chargés dans la page "
        f"({q.summary()})."
        f"{lignes_alt}"
    )


# ── Claude API (optionnel) ──
def _build_claude_reply(q: ConciergeQuery, picks: list[dict]) -> str:
    """Appelle l'API Claude pour rédiger une réponse plus naturelle.
    Fallback sur _build_local_reply si erreur.
    """
    try:
        import requests
        key = os.getenv("ANTHROPIC_API_KEY") or _get_anthropic_secret()
        if not key:
            return _build_local_reply(q, picks)
        ctx_restos = "\n".join(
            f"- {r.get('name', '?')} | {r.get('rating', '?')}★ | "
            f"{r.get('review_count', 0)} avis | {', '.join(r.get('location', {}).get('display_address', [])[:2])}"
            for r in picks
        ) or "Aucun restaurant ne matche parfaitement."
        system = (
            "Tu es Emma, une concierge IA bienveillante qui recommande des restaurants à Paris. "
            "Réponds en français, court (max 120 mots), chaleureux, avec 1 emoji au début. "
            "Mentionne le nom du 1er restaurant et justifie en 1 phrase."
        )
        user = (
            f"Demande utilisateur : « {q.raw} »\n"
            f"Critères extraits : {q.summary()}\n"
            f"Restaurants candidats :\n{ctx_restos}\n"
            f"Rédige la recommandation."
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
                "max_tokens": 300,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        text_parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        return "".join(text_parts).strip() or _build_local_reply(q, picks)
    except Exception:
        return _build_local_reply(q, picks)


def _get_anthropic_secret() -> str:
    """Lire ANTHROPIC_API_KEY depuis Streamlit secrets si dispo."""
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return ""


def recommend(text: str, restos: list[dict] | None = None) -> ConciergeReply:
    """Point d'entrée principal — mode conversation (legacy).

    Préférer `apply_to_session_state()` pour le mode "pilote la sidebar".
    """
    q = parse_query(text)
    pool = restos or []
    filtered = _filter_restaurants(pool, q) if pool else []
    picks = _rank(filtered, q) if filtered else []

    if not pool:
        return ConciergeReply(
            text=(
                f"J'ai compris votre demande ({q.summary()}). "
                "Lancez d'abord une recherche dans la barre latérale, "
                "puis demandez-moi une reco sur les résultats chargés."
            ),
            query=q,
            restaurants=[],
            source="local-template",
        )

    use_claude = bool(os.getenv("ANTHROPIC_API_KEY") or _get_anthropic_secret())
    if use_claude:
        text_reply = _build_claude_reply(q, picks)
        source = "claude-api"
    else:
        text_reply = _build_local_reply(q, picks)
        source = "local-template"

    return ConciergeReply(
        text=text_reply,
        query=q,
        restaurants=picks,
        source=source,
    )


def apply_to_session_state(text: str, st_module) -> ConciergeQuery:
    """Mode "pilote la sidebar" : parse la demande et injecte les critères
    dans `st.session_state.concierge_pending` pour que la sidebar les utilise
    au prochain rerun.

    Retourne la query parsée pour affichage/feedback.
    """
    q = parse_query(text)
    pending = {
        "arr": q.arrondissement,        # label FR ex: "11e" ou None
        "cat": q.category,              # label FR ex: "Italien" ou None
        "tri": "rating",                # défaut pertinent
        "prix": [q.price] if q.price else [],
    }
    st_module.session_state["concierge_pending"] = pending
    return q


# ── Tests inline ──
if __name__ == "__main__":
    fake = [
        {"name": "Pizzeria Popolare", "rating": 4.6, "review_count": 2300,
         "categories": ["italian", "pizza"], "price_level": 2,
         "location": {"display_address": ["Popolare", "75011 Paris"]}},
        {"name": "Big Love Cafe", "rating": 4.5, "review_count": 1800,
         "categories": ["italian"], "price_level": 2,
         "location": {"display_address": ["Big Love", "75011 Paris"]}},
        {"name": "Sushi Yuki", "rating": 4.7, "review_count": 950,
         "categories": ["japanese", "sushi"], "price_level": 3,
         "location": {"display_address": ["Yuki", "75009 Paris"]}},
        {"name": "Bao & Me", "rating": 4.4, "review_count": 620,
         "categories": ["chinese", "vietnamese"], "price_level": 1,
         "location": {"display_address": ["Bao", "75013 Paris"]}},
    ]
    tests = [
        "Je veux un resto italien romantique à Paris",
        "Un truc pas cher dans le 11e",
        "Sushi pour deux ce soir",
        "Bon vegan dans le 10e",
    ]
    for t in tests:
        rep = recommend(t, fake)
        print(f"--- {t!r}\n  critères: {rep.query.summary()}\n  source: {rep.source}\n  {rep.text}\n")
