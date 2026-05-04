import os
from dotenv import load_dotenv

load_dotenv()

YELP_API_KEY = os.getenv("YELP_API_KEY", "")
YELP_BASE_URL = "https://api.yelp.com/v3"

PARIS_ARRONDISSEMENTS = {
    "Tous": None,
    "1er": "75001",
    "2e": "75002",
    "3e": "75003",
    "4e": "75004",
    "5e": "75005",
    "6e": "75006",
    "7e": "75007",
    "8e": "75008",
    "9e": "75009",
    "10e": "75010",
    "11e": "75011",
    "12e": "75012",
    "13e": "75013",
    "14e": "75014",
    "15e": "75015",
    "16e": "75016",
    "17e": "75017",
    "18e": "75018",
    "19e": "75019",
    "20e": "75020",
}

# Label affiché → slug Yelp (l'API exige des slugs anglais)
CATEGORIES = {
    "Tous": None,
    "Français": "french",
    "Italien": "italian",
    "Japonais": "japanese",
    "Chinois": "chinese",
    "Thaï": "thai",
    "Indien": "indian",
    "Mexicain": "mexican",
    "Libanais": "lebanese",
    "Coréen": "korean",
    "Vietnamien": "vietnamese",
    "Grec": "greek",
    "Espagnol": "spanish",
    "Créperie": "creperies",
    "Brasserie": "brasseries",
    "Bistro": "bistros",
    "Street Food": "streetvendors",
    "Sushi": "sushi",
    "Pizza": "pizza",
    "Burger": "burgers",
    "Vegan": "vegan",
    "Glacier": "icecream",
    "Boulangerie": "bakeries",
    "Fruits de mer": "seafood",
    "Steakhouse": "steak",
}

PRICE_LABELS = {
    1: "€   (≤25€)",
    2: "€€  (25-50€)",
    3: "€€€ (50-100€)",
    4: "€€€€ (≥100€)",
}

MAX_RESULTS = 10


def get_secret(key, default=""):
    """Lire depuis Streamlit secrets (déployé) ou .env (local)."""
    try:
        import streamlit as st
        val = st.secrets[key] if key in st.secrets else ""
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key, default)


def score_pertinent(rating, review_count):
    """Score bayésien qui équilibre note et volume d'avis.
    Plus d'avis = plus de confiance dans la note.
    Formule: score = (rating * review_count + 3.5 * C) / (review_count + C)
    C = 25 (poids du prior — équivaut à "25 avis à 3.5/5" par défaut)
    """
    C = 25
    return round((rating * review_count + 3.5 * C) / (review_count + C), 2)