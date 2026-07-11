import streamlit as st
from config import PARIS_ARRONDISSEMENTS, CATEGORIES, PRICE_LABELS, MAX_RESULTS, score_pertinent
from yelp_client import YelpClient, PARIS_ARRONDISSEMENT_COORDS
from google_client import GoogleClient
from foursquare_client import FoursquareClient
from merger import merge_results
from concierge import apply_to_session_state as concierge_apply, parse_query as concierge_parse
from review_summarizer import summarize_for_restaurant, render_summary_markdown
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
if "concierge_history" not in st.session_state:
    st.session_state.concierge_history = []
if "reservations" not in st.session_state:
    st.session_state.reservations = []
if "user_reviews" not in st.session_state:
    st.session_state.user_reviews = []


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
    /* ── Hero landing ── */
    .hero-section {
        background: linear-gradient(135deg, rgba(255,240,245,0.95), rgba(248,187,208,0.85));
        border-radius: 24px;
        padding: 48px 32px;
        margin-bottom: 24px;
        text-align: center;
        box-shadow: 0 8px 30px rgba(233, 30, 99, 0.15);
        border: 1px solid rgba(244, 143, 177, 0.3);
    }
    .hero-section h1 {
        font-size: 3.2rem !important;
        font-weight: 800 !important;
        background: linear-gradient(90deg, #ad1457, #e91e63, #f06292);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 12px !important;
    }
    .hero-section p {
        color: #880e4f;
        font-size: 1.15rem;
        margin-bottom: 8px;
    }
    .hero-stats {
        display: flex;
        justify-content: center;
        gap: 40px;
        margin-top: 24px;
        flex-wrap: wrap;
    }
    .hero-stat {
        text-align: center;
    }
    .hero-stat .num {
        font-size: 2rem;
        font-weight: 800;
        color: #e91e63;
    }
    .hero-stat .lbl {
        font-size: 0.85rem;
        color: #880e4f;
    }
    /* ── Reservation form ── */
    .reservation-card {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 15px rgba(233, 30, 99, 0.12);
        border: 1px solid rgba(244, 143, 177, 0.3);
    }
    .reservation-success {
        background: linear-gradient(135deg, #f8bbd0, #f48fb1);
        color: white;
        padding: 16px 20px;
        border-radius: 12px;
        margin-top: 12px;
        font-weight: 600;
    }
    /* ── Concierge widget ── */
    .concierge-box {
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 340px;
        max-height: 480px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 8px 30px rgba(233, 30, 99, 0.25);
        border: 1px solid rgba(244, 143, 177, 0.4);
        z-index: 9999;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    .concierge-header {
        background: linear-gradient(135deg, #e91e63, #f06292);
        color: white;
        padding: 12px 16px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .concierge-body {
        padding: 12px 16px;
        max-height: 320px;
        overflow-y: auto;
        font-size: 0.88rem;
        color: #444;
    }
    .concierge-msg-user {
        background: #fce4ec;
        padding: 8px 12px;
        border-radius: 12px 12px 2px 12px;
        margin-bottom: 8px;
        color: #880e4f;
        text-align: right;
    }
    .concierge-msg-bot {
        background: linear-gradient(135deg, #f8bbd0, #f48fb1);
        color: white;
        padding: 8px 12px;
        border-radius: 12px 12px 12px 2px;
        margin-bottom: 8px;
    }
    .concierge-meta {
        font-size: 0.7rem;
        color: #999;
        margin-bottom: 12px;
        text-align: right;
    }
    /* ── Sentiment widget ── */
    .sentiment-box {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 12px;
        padding: 16px;
        margin-top: 12px;
        border: 1px solid rgba(244, 143, 177, 0.3);
    }
    .sentiment-badge {
        display: inline-block;
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.95rem;
    }
    .sentiment-positif { background: linear-gradient(135deg, #4caf50, #81c784); color: white; }
    .sentiment-negatif { background: linear-gradient(135deg, #e53935, #ef5350); color: white; }
    .sentiment-neutre  { background: linear-gradient(135deg, #9e9e9e, #bdbdbd); color: white; }
    .sentiment-mixte   { background: linear-gradient(135deg, #ff9800, #ffb74d); color: white; }
    .sentiment-meter {
        height: 8px;
        background: #fce4ec;
        border-radius: 4px;
        margin-top: 12px;
        overflow: hidden;
    }
    .sentiment-meter-fill {
        height: 100%;
        background: linear-gradient(90deg, #e53935, #9e9e9e, #4caf50);
        transition: width 0.3s;
    }
    /* ── Documentation IA ── */
    .doc-card {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 16px;
        padding: 24px;
        margin-top: 24px;
        border: 2px solid #e91e63;
        box-shadow: 0 4px 15px rgba(233, 30, 99, 0.15);
    }
    .doc-card h3 {
        color: #880e4f;
        margin-bottom: 12px;
    }
    .doc-item {
        padding: 12px;
        background: #fce4ec;
        border-radius: 10px;
        margin-bottom: 8px;
    }
    .doc-item strong {
        color: #ad1457;
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
# Valeurs pilotables par le concierge IA via session_state
if "concierge_pending" not in st.session_state:
    st.session_state.concierge_pending = None  # dict critères à appliquer

with st.sidebar:
    st.markdown("### 🎀 Your criteria")

    # Valeurs par défaut pilotables par le concierge
    arr_options = list(PARIS_ARRONDISSEMENTS.keys())
    cat_options = list(CATEGORIES.keys())
    tri_options = ["rating", "best_match", "review_count", "distance"]

    # Si le concierge a injecté des critères, on les utilise comme défaut
    pending = st.session_state.concierge_pending
    default_arr = pending.get("arr") if pending else None
    default_cat = pending.get("cat") if pending else None
    default_tri = pending.get("tri") if pending else None
    default_prix = pending.get("prix") if pending else None

    idx_arr = arr_options.index(default_arr) if default_arr in arr_options else 0
    idx_cat = cat_options.index(default_cat) if default_cat in cat_options else 0
    idx_tri = tri_options.index(default_tri) if default_tri in tri_options else 0

    arr = st.selectbox("District", arr_options, index=idx_arr, key="sb_arr")
    cat_label = st.selectbox("Cuisine type", cat_options, index=idx_cat, key="sb_cat")
    prix = st.multiselect("Budget", list(PRICE_LABELS.keys()),
                          default=default_prix if default_prix else [],
                          format_func=lambda x: PRICE_LABELS[x], key="sb_prix")
    tri = st.selectbox("Sort by", tri_options, index=idx_tri, key="sb_tri")

    # Auto-recherche si le concierge a injecté des critères
    auto_search = pending is not None
    if auto_search:
        st.session_state.concierge_pending = None  # consume

    # Sources
    available_yelp = yelp.available if hasattr(yelp, 'available') else True
    available_google = google.available
    available_foursquare = foursquare.available

    st.markdown("---")
    st.markdown("### 📡 Sources")  # label stays — "Sources" is identical in EN/FR

    sources_labels = []
    if available_yelp:
        sources_labels.append("Yelp")
    if available_google:
        sources_labels.append("Google Places")
    if available_foursquare:
        sources_labels.append("Foursquare")

    if not sources_labels:
        st.warning("⚠️ No API key configured. Add your keys in `.env`")
        enabled_sources = []
    else:
        default_sources = sources_labels.copy()
        enabled_sources = st.multiselect(
            "Activer les sources", sources_labels,
            default=default_sources
        )

    # ── Fonction de recherche (réutilisée par bouton + concierge) ──
    def run_search():
        arr_key = arr if arr != "Tous" else None
        cat_slug = CATEGORIES.get(cat_label) if cat_label != "Tous" else None
        price_str = ",".join(str(p) for p in prix) if prix else None

        all_results = {}
        errors = []

        with st.spinner("Searching for the best restaurants..."):
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

    do_search = st.button("🔍 Search", use_container_width=True, disabled=not enabled_sources)
    if do_search or auto_search:
        if enabled_sources:
            run_search()

    # ── Favoris ──
    if st.session_state.favorites:
        st.markdown("---")
        st.markdown(f"### 💖 Favorites ({len(st.session_state.favorites)})")
        if st.button("🗑️ Clear all", use_container_width=True):
            st.session_state.favorites = []
            st.rerun()


# ── Header / Hero landing ──
st.markdown("""
<div class="hero-section">
    <h1>Emma Rosstaurant</h1>
    <p>The best tables in Paris, picked for you by a food-loving AI.</p>
    <p style="font-size:0.95rem;opacity:0.85;">3 APIs crossed • Bayesian scoring • AI concierge • Sentiment analysis</p>
    <div class="hero-stats">
        <div class="hero-stat"><div class="num">3</div><div class="lbl">API sources</div></div>
        <div class="hero-stat"><div class="num">20</div><div class="lbl">Districts</div></div>
        <div class="hero-stat"><div class="num">24</div><div class="lbl">Cuisines</div></div>
    </div>
</div>
""", unsafe_allow_html=True)

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
    st.info("Configure your API keys in `.env` to enable sources.\n\n"
            "- `YELP_API_KEY` (already configured)\n"
            "- `GOOGLE_PLACES_API_KEY`\n"
            "- `FOURSQUARE_API_KEY`")


# ── Favoris en haut ──
if st.session_state.favorites:
    with st.expander(f"💖 My favorites ({len(st.session_state.favorites)})", expanded=False):
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
                    <span class="card-score-badge">Score: {sc}</span>
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
    summary_key = f"summary_{biz.get('id', i)}"

    st.markdown(f"""
    <div class="restaurant-card">
        <div class="card-top">
            {photo_html}
            <div class="card-info">
                <div class="card-name">{name} {source_html}</div>
                <div class="card-rating">{'⭐' * int(rating)} {rating} ({review_count} reviews) — {price}</div>
                <div class="card-meta">📍 {addr}</div>
                <div class="card-meta">🍜 {categories}</div>
                <span class="card-score-badge">Score: {sc}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
    with col1:
        if st.button(f"{heart} Favorite", key=f"fav_{biz.get('id', i)}"):
            biz_id = biz.get("id")
            if is_fav:
                st.session_state.favorites = [f for f in st.session_state.favorites if f.get("id") != biz_id]
            else:
                st.session_state.favorites.append(biz)
            st.rerun()
    with col2:
        if st.button("💬 Reviews", key=f"rev_btn_{biz.get('id', i)}"):
            st.session_state[review_key] = not st.session_state.get(review_key, False)
            st.session_state[summary_key] = False
            st.rerun()
    with col3:
        if st.button("🤖 AI Summary", key=f"sum_btn_{biz.get('id', i)}"):
            st.session_state[summary_key] = not st.session_state.get(summary_key, False)
            st.session_state[review_key] = False
            st.rerun()
    with col4:
        if url:
            st.markdown(f"[View online →]({url})")

    # ── Résumé IA des avis ──
    if st.session_state.get(summary_key, False):
        with st.spinner("Emma is analyzing reviews with AI..."):
            summary = summarize_for_restaurant(biz, yelp_client=yelp, google_client=google)
        st.markdown(render_summary_markdown(summary), unsafe_allow_html=True)
        st.markdown("---")

    # ── Reviews brutes ──
    if st.session_state.get(review_key, False):
        primary_source = sources[0] if sources else "yelp"
        with st.spinner("Loading reviews..."):
            if primary_source == "google" and google.available:
                reviews, err = google.get_reviews(biz.get("id", ""))
            elif primary_source == "foursquare" and foursquare.available:
                # Foursquare n'a pas d'endpoint reviews direct, fallback Yelp si dispo
                reviews, err = [], None
            else:
                reviews, err = yelp.get_reviews(biz.get("id", ""))

        if err:
            st.warning(f"Could not load reviews: {err}")
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
            st.info("No reviews available.")
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
                f'{len(results)} unique restaurants ({detail_str})</p>',
                unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# Section Laisser un avis — démo SentimentAnalysis (Specialized AI)
# ════════════════════════════════════════════════════════════════════
# Emma AI Concierge — pilote la sidebar via langage naturel
# ════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("""
<div class="concierge-box" id="emma-concierge">
    <div class="concierge-header">
        <span style="font-size:1.4rem;">🎀</span>
        <div>
            <div style="line-height:1.1;">Emma AI Concierge</div>
            <div style="font-size:0.7rem;opacity:0.85;font-weight:400;">Tell me what you want — I'll set the filters</div>
        </div>
    </div>
    <div class="concierge-body">
        <div class="concierge-msg-bot">
            Type your request (e.g. "a pizzeria in the 5th", "a cheap Japanese in the 11th")
            — I'll update the filters and launch the search. 🌸
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Historique
for msg in st.session_state.concierge_history:
    if msg["role"] == "user":
        st.markdown(f'<div class="concierge-msg-user">{msg["text"]}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="concierge-msg-bot">{msg["text"]}</div>',
                    unsafe_allow_html=True)

col_c1, col_c2 = st.columns([4, 1])
with col_c1:
    user_msg = st.text_input(
        "Ask Emma...",
        key="concierge_input",
        placeholder="e.g. I want a pizzeria in the 5th",
        label_visibility="collapsed",
    )
with col_c2:
    if st.button("Send", use_container_width=True):
        if user_msg.strip():
            q = concierge_apply(user_msg, st)
            st.session_state.concierge_history.append({"role": "user", "text": user_msg})
            crit = q.summary()
            st.session_state.concierge_history.append({
                "role": "bot",
                "text": f"Got it! Filters set to: {crit}. Searching... 🎀",
            })
            st.rerun()

if st.button("Clear conversation", use_container_width=True):
    st.session_state.concierge_history = []
    st.rerun()


# ════════════════════════════════════════════════════════════════════
# Footer
# ════════════════════════════════════════════════════════════════════
st.markdown("""
<p style="text-align:center;color:#ad1457;font-size:0.8rem;margin-top:32px;">
Emma Rosstaurant 🎀
</p>
""", unsafe_allow_html=True)