# Emma Rosstaurant 🎀

Site de recommandation de restaurants à Paris, intégrant 3 outils d'IA.
Projet HWR Berlin.

## Démonstration en ligne

L'application est déployée sur Streamlit Community Cloud.

## Outils IA implémentés

### 1. Claude Code — Code AI
Génération & architecture de l'application. Le code a été structuré avec
Claude Code (Anthropic) : `app.py`, `concierge.py`, `sentiment.py`,
`merger.py`, clients API (`yelp_client.py`, `google_client.py`,
`foursquare_client.py`).

### 2. Emma AI Concierge — Content AI
Moteur de recommandation conversationnel (`concierge.py`). L'utilisateur
tape une demande en langage naturel français, par exemple :

> « Je veux un resto italien romantique à Paris »
> « Un truc pas cher dans le 11e »
> « Sushi pour deux ce soir »

L'IA parse la demande (catégorie, arrondissement, prix, ambiance), filtre
les résultats déjà chargés dans la page, et rédige une recommandation
personnalisée en prose.

Si `ANTHROPIC_API_KEY` est définie (`.env` ou Streamlit secrets), le
concierge appelle l'API Claude (modèle `claude-haiku-4-5`) pour une
génération plus naturelle. Sinon, fallback déterministe sur templates FR.

### 3. SentimentAnalysis — Specialized AI
Analyse de sentiment temps réel des avis utilisateurs (`sentiment.py`).
Lexique pondéré français inspiré de FEEL/LiLaH, ~150 entrées adaptées au
domaine restauration. Gère :

- polarité lexicale (positif / négatif)
- intensificateurs (`très`, `vraiment`, `super`, `hyper`…)
- négations (`ne…pas`, `aucun`, `jamais`, `sans`…)
- bigrammes (`pas terrible`, `très bon`, `trop cher`, `à éviter`…)

Retourne un `SentimentResult` : label (Positif/Négatif/Neutre/Mixte),
score normalisé [-1, +1], confiance [0, 1], et suggestion d'étoiles 1-5.
Exécution 100% locale, déterministe, aucun appel API.

L'UI affiche en temps réel pendant la frappe :
- un badge coloré `IA Sentiment : Positif 😊 — score +0.72 (conf. 90%)`
- une jauge visuelle [-1, +1]
- la suggestion d'étoiles
- les tokens positifs/négatifs détectés

## Stack technique

- Python 3.11
- Streamlit (UI)
- Yelp Fusion API, Google Places API v1, Foursquare API v3
- Folium (carte interactive)
- python-dotenv (secrets)
- Anthropic SDK (optionnel, pour concierge LLM)

## Installation locale

```bash
cd emma-rosstaurant
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # remplir les clés
streamlit run app.py
```

## Structure

```
emma-rosstaurant/
├── app.py              # UI Streamlit (hero, carte, cards, réservation, avis, concierge, doc)
├── config.py           # Arrondissements, catégories, prix, score bayésien
├── yelp_client.py      # Client Yelp Fusion
├── google_client.py    # Client Google Places v1
├── foursquare_client.py# Client Foursquare v3
├── merger.py           # Déduplication cross-source (SequenceMatcher + Haversine)
├── sentiment.py        # Specialized AI — analyse de sentiment FR
├── concierge.py        # Content AI — concierge conversationnel
├── requirements.txt
└── .env.example
```

## Tests rapides

```bash
python3.11 sentiment.py    # démo sur 7 avis types
python3.11 concierge.py    # démo sur 4 requêtes types
```
