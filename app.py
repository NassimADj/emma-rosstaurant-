import streamlit as st
from config import PARIS_ARRONDISSEMENTS, CATEGORIES, PRICE_LABELS, MAX_RESULTS, score_pertinent
from yelp_client import YelpClient, PARIS_ARRONDISSEMENT_COORDS
from google_client import GoogleClient
from foursquare_client import FoursquareClient
from merger import merge_results
import folium
from streamlit_folium import st_folium


# ── Initialisation ──
yelp = YelpClient()
google = GoogleClient()
foursquare = FoursquareClient()

if "favorites" not in st.session_state:
    st.session_state.favorites = []
if "results" not in st.session_state:
    st.session_state.results = []
if "total" not in st.session_state:
    st.session_state.total = 0
if "offset" not in st.session_state:
    st.session_state.offset = 0


# ── CSS girly ──
CUSTOM_CSS = """
<style>
    .stApp {
        background: linear-gradient(135deg, #fff0f5 0%, #fce4ec 30%, #f8bbd0 70%, #f48fb1 100%);
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8bbd0 0%, #f48fb1 100%) !important;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stCaption {
        color: #880e4f !important;
        font-weight: 600;
    }
    .stSelectbox > div > div > div,
    .stMultiSelect > div > div > div {
        background-color: #fce4ec !important;
        border: 1px solid rgba(244, 143, 177, 0.5) !important;
        border-radius: 10px !important;
        color: #880e4f !important;
    }
    .stSelectbox label, .stMultiSelect label {
        color: #880e4f !important;
    }
    .stMultiSelect [data-baseweb="tag"] {
        background-color: #f06292 !important;
        color: white !important;
        border-radius: 12px !important;
    }
    .stMultiSelect [data-baseweb="tag"] span {
        color: white !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #e91e63, #f06292) !important;
        color: white !important;
        border: none !important;
        border-radius: 20px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #c2185b, #e91e63) !important;
        color: white !important;
    }
    .main-title {
        font-size: 2.8rem !important;
        font-weight: 800 !important;
        background: linear-gradient(90deg, #ad1457, #e91e63, #f06292);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 0 !important;
    }
    .main-subtitle {
        text-align: center;
        color: #ad1457 !important;
        font-size: 1.1rem !important;
        font-weight: 500;
        margin-top: 0 !important;
    }
    .restaurant-card {
        background: rgba(255, 255, 255, 0.85);
        border-radius: 16px;
        padding: 20px 24px;
        margin-bottom: 16px;
        box-shadow: 0 4px 15px rgba(233, 30, 99, 0.12);
        border: 1px solid rgba(244, 143, 177, 0.3);
        backdrop-filter: blur(8px);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .restaurant-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(233, 30, 99, 0.2);
    }
    .card-top {
        display: flex;
        align-items: flex-start;
        gap: 16px;
    }
    .card-photo {
        width: 100px;
        height: 100px;
        border-radius: 12px;
        object-fit: cover;
        flex-shrink: 0;
        border: 2px solid rgba(244, 143, 177, 0.4);
    }
    .card-photo-placeholder {
        width: 100px;
        height: 100px;
        border-radius: 12px;
        flex-shrink: 0;
        background: linear-gradient(135deg, #fce4ec, #f8bbd0);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.5rem;
    }
    .card-info {
        flex: 1;
        min-width: 0;
    }
    .card-name {
        font-size: 1.3rem;
        font-weight: 700;
        color: #880e4f;
        margin-bottom: 4px;
    }
    .card-rating {
        color: #e91e63;
        font-weight: 600;
        font-size: 0.95rem;
    }
    .card-meta {
        color: #555;
        font-size: 0.85rem;
        margin-top: 4px;
    }
    .card-score-badge {
        background: linear-gradient(135deg, #e91e63, #f06292);
        color: white;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 700;
        display: inline-block;
        margin-top: 6px;
    }
    .source-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.7rem;
        font-weight: 600;
        margin-left: 6px;
    }
    .source-yelp { background: #ff1a1a; color: white; }
    .source-google { background: #4285F4; color: white; }
    .source-foursquare { background: #0732a2; color: white; }
    .review-item {
        background: rgba(248, 187, 208, 0.15);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .review-user { font-weight: 600; color: #880e4f; font-size: 0.85rem; }
    .review-text { color: #444; font-size: 0.85rem; margin-top: 4px; line-height: 1.4; }
    .review-rating { color: #e91e63; }
    .map-section {
        border-radius: 16px;
        overflow: hidden;
        margin-bottom: 20px;
        border: 2px solid rgba(244, 143, 177, 0.4);
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── Badge source HTML ──
def source_badge_html(sources):
    badges = {
        "yelp": '<span class="source-badge source-yelp">Yelp</span>',
        "google": '<span class="source-badge source-google">Google</span>',
        "foursquare": '<span class="source-badge source-foursquare">Foursquare</span>',
    }
    return " ".join(badges.get(s, "") for s in sources)


# ── Sidebar ──
with st.sidebar:
    st.markdown("### 🎀 Tes critères")

    arr = st.selectbox("Arrondissement", list(PARIS_ARRONDISSEMENTS.keys()))
    cat_label = st.selectbox("Type de cuisine", list(CATEGORIES.keys()))
    prix = st.multiselect("Budget", list(PRICE_LABELS.keys()),
                          format_func=lambda x: PRICE_LABELS[x])
    tri = st.selectbox("Trier par", ["rating", "best_match", "review_count", "distance"])

    # Sources
    available_yelp = yelp.available if hasattr(yelp, 'available') else True
    available_google = google.available
    available_foursquare = foursquare.available

    st.markdown("---")
    st.markdown("### 📡 Sources")

    sources_labels = []
    if available_yelp:
        sources_labels.append("Yelp")
    if available_google:
        sources_labels.append("Google Places")
    if available_foursquare:
        sources_labels.append("Foursquare")

    if not sources_labels:
        st.warning("⚠️ Aucune clé API configurée. Ajoute tes clés dans `.env`")
        enabled_sources = []
    else:
        default_sources = sources_labels.copy()
        enabled_sources = st.multiselect(
            "Activer les sources", sources_labels,
            default=default_sources
        )

    if st.button("🔍 Rechercher", use_container_width=True, disabled=not enabled_sources):
        arr_key = arr if arr != "Tous" else None
        cat_slug = CATEGORIES.get(cat_label) if cat_label != "Tous" else None
        price_str = ",".join(str(p) for p in prix) if prix else None

        all_results = {}
        errors = []

        with st.spinner("Je cherche les meilleurs restos..."):
            # Yelp
            if "Yelp" in enabled_sources and available_yelp:
                biz, err, total = yelp.search(
                    arrondissement=arr_key,
                    categories=cat_slug,
                    price=price_str,
                    sort_by=tri,
                )
                if err:
                    errors.append(f"Yelp: {err}")
                else:
                    for b in biz:
                        b["source"] = "yelp"
                    all_results["yelp"] = biz
                    st.session_state.yelp_total = total

            # Google Places
            if "Google Places" in enabled_sources and available_google:
                biz, err, total = google.search(
                    arrondissement=arr_key,
                    categories=cat_slug,
                    price=price_str,
                    sort_by=tri,
                )
                if err:
                    errors.append(f"Google: {err}")
                else:
                    for b in biz:
                        b["source"] = "google"
                    all_results["google"] = biz

            # Foursquare
            if "Foursquare" in enabled_sources and available_foursquare:
                biz, err, total = foursquare.search(
                    arrondissement=arr_key,
                    categories=cat_slug,
                    price=price_str,
                    sort_by=tri,
                )
                if err:
                    errors.append(f"Foursquare: {err}")
                else:
                    for b in biz:
                        b["source"] = "foursquare"
                    all_results["foursquare"] = biz

        if errors:
            for e in errors:
                st.warning(e)

        merged = merge_results(all_results) if all_results else []
        st.session_state.results = merged
        st.session_state.total = len(merged)
        st.session_state.offset = 0
        st.session_state.all_results = all_results

    # ── Favoris ──
    if st.session_state.favorites:
        st.markdown("---")
        st.markdown(f"### 💖 Favoris ({len(st.session_state.favorites)})")
        if st.button("🗑️ Effacer tout", use_container_width=True):
            st.session_state.favorites = []
            st.rerun()


# ── Header ──
st.markdown('<h1 class="main-title">Emma Rosstaurant</h1>', unsafe_allow_html=True)
st.markdown('<p class="main-subtitle">Les meilleurs restos de Paris, choisis pour toi</p>', unsafe_allow_html=True)

# ── Sources actives ──
active_sources = []
if yelp.available if hasattr(yelp, 'available') else True:
    active_sources.append("Yelp")
if google.available:
    active_sources.append("Google Places")
if foursquare.available:
    active_sources.append("Foursquare")

if active_sources:
    emoji_map = {"Yelp": "🔴", "Google Places": "🔵", "Foursquare": "🟣"}
    badges = " ".join(f"{emoji_map.get(s, '⚪')} {s}" for s in active_sources)
    st.markdown(f'<p style="text-align:center;color:#880e4f;font-size:0.85rem;">{badges}</p>',
                unsafe_allow_html=True)
elif not enabled_sources:
    st.info("Configure tes clés API dans `.env` pour activer les sources.\n\n"
            "- `YELP_API_KEY` (déjà configuré)\n"
            "- `GOOGLE_PLACES_API_KEY`\n"
            "- `FOURSQUARE_API_KEY`")


# ── Favoris en haut ──
if st.session_state.favorites:
    with st.expander(f"💖 Mes favoris ({len(st.session_state.favorites)})", expanded=False):
        for fav in st.session_state.favorites:
            name = fav.get("name", "?")
            rating = fav.get("rating", 0)
            review_count = fav.get("review_count", 0)
            url = fav.get("url", "#")
            addr = fav.get("address", "") or ", ".join(fav.get("location", {}).get("display_address", []))
            sc = score_pertinent(rating, review_count)
            sources = fav.get("sources", [fav.get("source", "yelp")])
            source_html = source_badge_html(sources)

            st.markdown(f"""
            <div class="restaurant-card">
                <div class="card-info">
                    <div class="card-name">{name} {source_html}</div>
                    <div class="card-rating">{'⭐' * int(rating)} {rating} ({review_count} avis)</div>
                    <div class="card-meta">📍 {addr}</div>
                    <span class="card-score-badge">Score {sc}</span>
                </div>
            </div>
            <a href="{url}" target="_blank" style="color:#e91e63;font-size:0.8rem;">Voir en ligne →</a>
            """, unsafe_allow_html=True)


# ── Carte interactive ──
results = st.session_state.results
if results:
    if arr != "Tous" and arr in PARIS_ARRONDISSEMENT_COORDS:
        center = PARIS_ARRONDISSEMENT_COORDS[arr]
        zoom = 14
    else:
        center = {"lat": 48.8566, "lon": 2.3522}
        zoom = 12

    marker_colors = {"yelp": "red", "google": "blue", "foursquare": "purple"}
    default_color = "pink"

    m = folium.Map(
        location=[center["lat"], center["lon"]],
        zoom_start=zoom,
        tiles="CartoDB Positron"
    )
    for biz in results:
        coords = biz.get("coordinates", {})
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if lat and lon:
            primary_source = biz.get("sources", ["yelp"])[0] if biz.get("sources") else biz.get("source", "yelp")
            color = marker_colors.get(primary_source, default_color)
            popup = folium.Popup(
                f"<b>{biz['name']}</b><br>{biz.get('rating', '?')}⭐ ({biz.get('review_count', 0)} avis)",
                max_width=250
            )
            folium.Marker(
                location=[lat, lon],
                popup=popup,
                tooltip=biz["name"],
                icon=folium.Icon(color=color, icon="cutlery", prefix="fa")
            ).add_to(m)

    st.markdown('<div class="map-section">', unsafe_allow_html=True)
    st_folium(m, width=700, height=400, returned_objects=[])
    st.markdown('</div>', unsafe_allow_html=True)

    # Légende
    legend_parts = []
    for src_name, color_hex in [("Yelp 🔴", "#ff1a1a"), ("Google 🔵", "#4285F4"), ("Foursquare 🟣", "#0732a2")]:
        if src_name.split(" ")[0].lower() in {s for biz in results for s in biz.get("sources", [biz.get("source", "")])}:
            legend_parts.append(f'<span style="color:{color_hex};font-weight:600;">{src_name}</span>')
    if legend_parts:
        st.markdown(f'<p style="text-align:center;font-size:0.8rem;">{" | ".join(legend_parts)}</p>',
                    unsafe_allow_html=True)


# ── Résultats ──
for i, biz in enumerate(results):
    name = biz.get("name", "???")
    rating = biz.get("rating", 0)
    review_count = biz.get("review_count", 0)
    url = biz.get("url", "#")
    price = biz.get("price", "")
    addr = biz.get("address", "") or ", ".join(biz.get("location", {}).get("display_address", []))
    categories = ", ".join(c["title"] for c in biz.get("categories", []))
    image_url = biz.get("image_url", "")
    is_fav = any(f.get("id") == biz.get("id") for f in st.session_state.favorites)
    sc = biz.get("score", score_pertinent(rating, review_count))
    sources = biz.get("sources", [biz.get("source", "yelp")])
    source_html = source_badge_html(sources)

    # Photo
    if image_url:
        photo_html = f'<img src="{image_url}" class="card-photo" alt="{name}">'
    else:
        photo_html = '<div class="card-photo-placeholder">🍽️</div>'

    heart = "❤️" if is_fav else "🤍"
    review_key = f"review_{biz.get('id', i)}"

    st.markdown(f"""
    <div class="restaurant-card">
        <div class="card-top">
            {photo_html}
            <div class="card-info">
                <div class="card-name">{name} {source_html}</div>
                <div class="card-rating">{'⭐' * int(rating)} {rating} ({review_count} avis) — {price}</div>
                <div class="card-meta">📍 {addr}</div>
                <div class="card-meta">🍜 {categories}</div>
                <span class="card-score-badge">Score {sc}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button(f"{heart} Favori", key=f"fav_{biz.get('id', i)}"):
            biz_id = biz.get("id")
            if is_fav:
                st.session_state.favorites = [f for f in st.session_state.favorites if f.get("id") != biz_id]
            else:
                st.session_state.favorites.append(biz)
            st.rerun()
    with col2:
        if st.button("💬 Avis", key=f"rev_btn_{biz.get('id', i)}"):
            st.session_state[review_key] = not st.session_state.get(review_key, False)
            st.rerun()
    with col3:
        if url:
            st.markdown(f"[Voir en ligne →]({url})")

    # ── Reviews ──
    if st.session_state.get(review_key, False):
        primary_source = sources[0] if sources else "yelp"
        with st.spinner("Chargement des avis..."):
            if primary_source == "google" and google.available:
                reviews, err = google.get_reviews(biz.get("id", ""))
            elif primary_source == "foursquare" and foursquare.available:
                # Foursquare n'a pas d'endpoint reviews direct, fallback Yelp si dispo
                reviews, err = [], None
            else:
                reviews, err = yelp.get_reviews(biz.get("id", ""))

        if err:
            st.warning(f"Impossible de charger les avis : {err}")
        elif reviews:
            for rev in reviews[:3]:
                user = rev.get("user", {}).get("name", "Anonyme")
                text = rev.get("text", "")
                rev_rating = rev.get("rating", 0)
                st.markdown(f"""
                <div class="review-item">
                    <span class="review-user">{user}</span>
                    <span class="review-rating">{'⭐' * int(rev_rating)}</span>
                    <div class="review-text">{text}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aucun avis disponible.")
        st.markdown("---")


# ── Info résultats ──
if results:
    sources_in_results = set()
    for biz in results:
        for s in biz.get("sources", [biz.get("source", "")]):
            sources_in_results.add(s)
    counts = {s: 0 for s in sources_in_results}
    for biz in results:
        for s in biz.get("sources", [biz.get("source", "")]):
            counts[s] = counts.get(s, 0) + 1
    detail = " + ".join(f"{counts.get('yelp', 0)} Yelp" for _ in [1] if "yelp" in counts)
    detail_parts = []
    if "yelp" in counts:
        detail_parts.append(f"{counts['yelp']} Yelp")
    if "google" in counts:
        detail_parts.append(f"{counts['google']} Google")
    if "foursquare" in counts:
        detail_parts.append(f"{counts['foursquare']} Foursquare")
    detail_str = " | ".join(detail_parts)
    st.markdown(f'<p style="text-align:center;color:#880e4f;font-size:0.85rem;">'
                f'{len(results)} restaurants uniques ({detail_str})</p>',
                unsafe_allow_html=True)