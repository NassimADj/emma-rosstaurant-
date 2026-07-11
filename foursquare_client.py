import requests
import os
from config import MAX_RESULTS, get_secret
from yelp_client import PARIS_ARRONDISSEMENT_COORDS

# Catégories Foursquare (IDs) — https://docs.foursquare.com/data-products/docs/categories
FOURSQUARE_CATEGORIES = {
    "french": "13065",       # French Restaurant
    "italian": "13068",      # Italian Restaurant
    "japanese": "13069",     # Japanese Restaurant
    "chinese": "13071",      # Chinese Restaurant
    "thai": "13072",          # Thai Restaurant
    "indian": "13073",        # Indian Restaurant
    "mexican": "13075",       # Mexican Restaurant
    "lebanese": "13076",     # Middle Eastern Restaurant
    "korean": "13078",        # Korean Restaurant
    "vietnamese": "13080",   # Vietnamese Restaurant
    "greek": "13081",         # Greek Restaurant
    "spanish": "13082",      # Spanish Restaurant
    "creperies": "13034",    # Creperie
    "brasseries": "13034",   # Brasserie (closest)
    "bistros": "13034",      # Bistro (closest)
    "streetvendors": "13145", # Food Truck / Street Food
    "sushi": "13069",         # Japanese (sushi)
    "pizza": "13105",         # Pizza Place
    "burgers": "13101",       # Burger Restaurant
    "vegan": "13314",         # Vegan & Vegetarian Restaurant
    "icecream": "13046",     # Ice Cream Shop
    "bakeries": "13039",     # Bakery
    "seafood": "13074",       # Seafood Restaurant
    "steak": "13047",         # Steakhouse
}


class FoursquareClient:
    BASE_URL = "https://api.foursquare.com/v3"

    def __init__(self):
        self._key = None

    @property
    def api_key(self):
        if self._key is None:
            self._key = get_secret("FOURSQUARE_API_KEY")
        return self._key

    @property
    def base(self):
        return self.BASE_URL

    @property
    def available(self):
        return bool(self.api_key)

    def _headers(self):
        return {
            "Accept": "application/json",
            "Authorization": self.api_key,
        }

    def search(self, arrondissement=None, categories=None, price=None,
               sort_by="rating", limit=MAX_RESULTS, offset=0):
        if not self.api_key:
            return [], "Clé API Foursquare manquante — ajoute FOURSQUARE_API_KEY dans .env", 0

        # Coordonnées
        if arrondissement and arrondissement in PARIS_ARRONDISSEMENT_COORDS:
            coords = PARIS_ARRONDISSEMENT_COORDS[arrondissement]
            ll = f"{coords['lat']},{coords['lon']}"
            radius = 4000
        else:
            ll = "48.8566,2.3522"
            radius = 5000

        params = {
            "ll": ll,
            "radius": radius,
            "limit": limit,
            "offset": offset,
            "fields": "fsq_id,name,geocodes,location,rating,price,stats,categories,photos,url",
        }

        # Catégorie
        if categories and categories in FOURSQUARE_CATEGORIES:
            params["categories"] = FOURSQUARE_CATEGORIES[categories]

        # Prix Foursquare (1-4)
        if price:
            price_levels = [int(p) for p in price.split(",")]
            # Foursquare utilisait price dans l'ancienne API,
            # la nouvelle n'a pas de filtre prix direct, on skip
            # mais on gardera pour filtrer côté client après

        # Sort
        if sort_by == "rating":
            params["sort"] = "RATING"
        elif sort_by == "distance":
            params["sort"] = "DISTANCE"
        # "best_match" et "review_count" n'ont pas d'équivalent direct

        # Query pour le type si pas de catégorie Foursquare
        if categories and categories not in FOURSQUARE_CATEGORIES:
            # Fallback: chercher par texte
            cat_name = categories.replace("_", " ").title()
            params["query"] = f"{cat_name} restaurant"

        try:
            r = requests.get(
                f"{self.base}/places/search",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            if r.status_code == 401 or r.status_code == 403:
                return [], "Clé API Foursquare invalide — vérifie ton .env", 0
            if r.status_code == 429:
                return [], "Limite d'appels Foursquare atteinte — réessaie plus tard", 0
            if r.status_code != 200:
                return [], f"Erreur Foursquare ({r.status_code})", 0

            data = r.json()
            results = data.get("results", [])

            # Normaliser
            businesses = [self._normalize(r) for r in results]

            # Filtrer par prix côté client si nécessaire
            if price:
                price_map_fs = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
                allowed = [price_map_fs.get(int(p), "") for p in price.split(",")]
                businesses = [b for b in businesses if b.get("price", "") in allowed]

            return businesses, None, len(businesses)

        except requests.Timeout:
            return [], "Foursquare ne répond pas — réessaie dans quelques secondes", 0
        except requests.ConnectionError:
            return [], "Pas de connexion internet", 0
        except Exception as e:
            return [], f"Erreur Foursquare: {e}", 0

    def _normalize(self, place):
        """Convertir un lieu Foursquare au format commun."""
        # Photo
        photos = place.get("photos", [])
        image_url = ""
        if photos:
            prefix = photos[0].get("prefix", "")
            suffix = photos[0].get("suffix", "")
            if prefix and suffix:
                image_url = f"{prefix}400x400{suffix}"

        # Coordonnées
        geo = place.get("geocodes", {}).get("main", {})
        lat = geo.get("latitude", 0)
        lon = geo.get("longitude", 0)

        # Adresse
        loc = place.get("location", {})
        address_parts = []
        if loc.get("address"):
            address_parts.append(loc["address"])
        if loc.get("locality"):
            address_parts.append(loc["locality"])
        if loc.get("postcode"):
            address_parts.append(loc["postcode"])
        address = ", ".join(address_parts)

        # Catégories
        cats = place.get("categories", [])
        categories = [{"title": c.get("name", "")} for c in cats if c.get("name")]

        # Rating
        rating = place.get("rating", 0) or 0
        stats = place.get("stats", {})
        review_count = stats.get("total_ratings", 0) or 0

        # Prix
        price = place.get("price", 0)
        price_map = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
        price_str = price_map.get(price, "")

        return {
            "id": place.get("fsq_id", ""),
            "name": place.get("name", "???"),
            "rating": rating,
            "review_count": review_count,
            "price": price_str,
            "address": address,
            "categories": categories,
            "image_url": image_url,
            "url": place.get("link", ""),
            "coordinates": {
                "latitude": lat,
                "longitude": lon,
            },
            "location": {"display_address": address_parts},
            "source": "foursquare",
        }