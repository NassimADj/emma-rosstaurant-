"""Merger — fusionne et déduplique les résultats de plusieurs sources API."""
from difflib import SequenceMatcher
from config import score_pertinent


def normalize_name(name):
    """Normalise un nom de restaurant pour la comparaison."""
    return (
        name.lower()
        .strip()
        .replace("'", " ")
        .replace("-", " ")
        .replace("ê", "e")
        .replace("é", "e")
        .replace("è", "e")
        .replace("à", "a")
        .replace("ù", "u")
        .replace("ç", "c")
    )


def are_duplicate(biz1, biz2, name_threshold=0.75, dist_threshold=150):
    """Détermine si deux résultats sont le même restaurant.

    Critères:
    - Noms similaires (SequenceMatcher ≥ threshold) OU noms identiques normalisés
    - ET distance < dist_threshold (en mètres)
    """
    n1 = normalize_name(biz1.get("name", ""))
    n2 = normalize_name(biz2.get("name", ""))

    name_similar = (
        n1 == n2
        or SequenceMatcher(None, n1, n2).ratio() >= name_threshold
    )

    # Vérifier la distance géographique
    c1 = biz1.get("coordinates", {})
    c2 = biz2.get("coordinates", {})
    lat1, lon1 = c1.get("latitude", 0), c1.get("longitude", 0)
    lat2, lon2 = c2.get("latitude", 0), c2.get("longitude", 0)

    if lat1 and lon1 and lat2 and lon2:
        # Distance approximative en mètres (Haversine simplifié)
        dist = haversine_meters(lat1, lon1, lat2, lon2)
        close_enough = dist < dist_threshold
    else:
        # Si pas de coords, on compare juste par adresse textuelle
        addr1 = ", ".join(biz1.get("location", {}).get("display_address", [])).lower()
        addr2 = ", ".join(biz2.get("location", {}).get("display_address", [])).lower()
        close_enough = addr1 and addr2 and addr1 == addr2

    return name_similar and close_enough


def haversine_meters(lat1, lon1, lat2, lon2):
    """Distance en mètres entre deux points GPS."""
    from math import radians, cos, sin, asin, sqrt
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def merge_results(all_results):
    """Fusionne les résultats de toutes les sources en dédupliquant.

    all_results: dict { "yelp": [...], "google": [...], "foursquare": [...] }
    Retourne: liste de dicts normalisés, triée par score bayésien décroissant.
    Chaque entrée a un champ "sources" listant les API qui ont ce resto.
    """
    merged = []
    seen = []

    for source_name, results in all_results.items():
        if not results:
            continue
        for biz in results:
            biz_with_source = {**biz, "sources": [source_name]}

            # Chercher un doublon dans merged
            found = False
            for i, existing in enumerate(merged):
                if are_duplicate(existing, biz):
                    # Fusionner : garder les infos les plus riches
                    merged[i] = merge_entry(existing, biz_with_source, source_name)
                    found = True
                    break

            if not found:
                merged.append(biz_with_source)

    # Trier par score bayésien
    for biz in merged:
        biz["score"] = score_pertinent(
            biz.get("rating", 0) or 0,
            biz.get("review_count", 0) or 0,
        )
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)
    return merged


def merge_entry(existing, new_entry, new_source):
    """Fusionne deux entrées du même restaurant.

    Garde les infos les plus riches (photo, le plus d'avis, etc.).
    """
    # Ajouter la source
    sources = list(set(existing.get("sources", []) + [new_source]))

    # Garder le meilleur rating (celui qui a le plus d'avis)
    if (new_entry.get("review_count") or 0) > (existing.get("review_count") or 0):
        rating = new_entry.get("rating", existing.get("rating", 0))
        review_count = new_entry.get("review_count", existing.get("review_count", 0))
    else:
        rating = existing.get("rating", 0)
        review_count = existing.get("review_count", 0)

    # Garder la meilleure photo
    image_url = existing.get("image_url") or new_entry.get("image_url") or ""

    # Garder l'URL la plus utile
    url = existing.get("url") or new_entry.get("url") or ""

    # Fusionner les catégories
    existing_cats = {c.get("title", "") for c in existing.get("categories", [])}
    new_cats = {c.get("title", "") for c in new_entry.get("categories", [])}
    all_cats = existing_cats | new_cats
    categories = [{"title": t} for t in all_cats if t]

    return {
        **existing,
        "rating": rating,
        "review_count": review_count,
        "sources": sources,
        "image_url": image_url,
        "url": url,
        "categories": categories,
    }