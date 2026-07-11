import requests
import os
from config import MAX_RESULTS, PARIS_ARRONDISSEMENTS, CATEGORIES, get_secret

# Mapping catégories → types Google Places
GOOGLE_TYPES = {
    "french": "french_restaurant",
    "italian": "italian_restaurant",
    "japanese": "japanese_restaurant",
    "chinese": "chinese_restaurant",
    "thai": "thai_restaurant",
    "indian": "indian_restaurant",
    "mexican": "mexican_restaurant",
    "lebanese": "lebanese_restaurant",
    "korean": "korean_restaurant",
    "vietnamese": "vietnamese_restaurant",
    "greek": "greek_restaurant",
    "spanish": "spanish_restaurant",
    "creperies": "restaurant",
    "brasseries": "brasserie",
    "bistros": "bistro",
    "streetvendors": "restaurant",
    "sushi": "sushi_restaurant",
    "pizza": "pizza_restaurant",
    "burgers": "hamburger_restaurant",
    "vegan": "vegan_restaurant",
    "icecream": "ice_cream_shop",
    "bakeries": "bakery",
    "seafood": "seafood_restaurant",
    "steak": "steak_house",
}


class GoogleClient:
    BASE_URL = "https://places.googleapis.com/v1"

    def __init__(self):
        self._key = None

    @property
    def api_key(self):
        if self._key is None:
            self._key = get_secret("GOOGLE_PLACES_API_KEY")
        return self._key

    @property
    def base(self):
        return self.BASE_URL

    @property
    def available(self):
        return bool(self.api_key)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
        }

    def _field_mask(self):
        return (
            "places.displayName,places.formattedAddress,places.rating,"
            "places.userRatingCount,places.priceLevel,places.googleMapsUri,"
            "places.primaryType,places.photos,places.location,"
            "places.id,places.types,places.internationalPhoneNumber"
        )

    def search(self, arrondissement=None, categories=None, price=None,
                sort_by="rating", limit=MAX_RESULTS, offset=0):
        if not self.api_key:
            return [], "Clé API Google Places manquante — ajoute GOOGLE_PLACES_API_KEY dans .env", 0

        # Construire la requête textuelle
        query_parts = ["restaurant"]
        if categories and categories in GOOGLE_TYPES:
            query_parts.append(GOOGLE_TYPES[categories])

        text_query = " ".join(query_parts) + " Paris"

        # Localisation
        if arrondissement and arrondissement in PARIS_ARRONDISSEMENT_COORDS:
            coords = PARIS_ARRONDISSEMENT_COORDS[arrondissement]
            location_bias = {
                "circle": {
                    "center": {"latitude": coords["lat"], "longitude": coords["lon"]},
                    "radius": 4000.0,
                }
            }
        else:
            location_bias = {
                "circle": {
                    "center": {"latitude": 48.8566, "longitude": 2.3522},
                    "radius": 5000.0,
                }
            }

        # Niveaux de prix Google (1=cheap, 2=moderate, 3=expensive, 4=very expensive)
        price_levels = None
        if price:
            price_levels = [int(p) for p in price.split(",")]

        body = {
            "textQuery": text_query,
            "locationBias": location_bias,
            "pageSize": limit,
            "languageCode": "fr",
        }
        if price_levels:
            body["priceLevels"] = price_levels

        headers = self._headers()
        headers["X-Goog-FieldMask"] = self._field_mask()

        try:
            r = requests.post(
                f"{self.base}/places:searchText",
                headers=headers,
                json=body,
                timeout=10,
            )
            if r.status_code == 401 or r.status_code == 403:
                return [], "Clé API Google Places invalide — vérifie ton .env", 0
            if r.status_code == 429:
                return [], "Limite d'appels Google atteinte — réessaie dans 1h", 0
            if r.status_code != 200:
                return [], f"Erreur Google Places ({r.status_code})", 0

            data = r.json()
            places = data.get("places", [])

            # Normaliser au format commun
            businesses = [self._normalize(p) for p in places]
            return businesses, None, len(businesses)

        except requests.Timeout:
            return [], "Google Places ne répond pas — réessaie dans quelques secondes", 0
        except requests.ConnectionError:
            return [], "Pas de connexion internet", 0
        except Exception as e:
            return [], f"Erreur Google: {e}", 0

    def _normalize(self, place):
        """Convertir un lieu Google Places au format commun."""
        # Photo
        photos = place.get("photos", [])
        image_url = ""
        if photos and photos[0].get("name"):
            photo_ref = photos[0]["name"]
            image_url = (
                f"https://places.googleapis.com/v1/{photo_ref}/media"
                f"?maxHeightPx=400&key={self.api_key}"
            )

        # Coordonnées
        loc = place.get("location", {})

        # Adresse
        address = place.get("formattedAddress", "")

        # Catégories
        types = place.get("types", [])
        primary = place.get("primaryType", "")

        # Prix
        price_level = place.get("priceLevel", "")
        price_map = {"PRICE_LEVEL_INEXPENSIVE": "€", "PRICE_LEVEL_MODERATE": "€€",
                     "PRICE_LEVEL_EXPENSIVE": "€€€", "PRICE_LEVEL_VERY_EXPENSIVE": "€€€€"}
        price_str = price_map.get(price_level, "")

        # Rating
        rating = place.get("rating", 0) or 0
        review_count = place.get("userRatingCount", 0) or 0

        return {
            "id": place.get("id", ""),
            "name": place.get("displayName", {}).get("text", "???"),
            "rating": rating,
            "review_count": review_count,
            "price": price_str,
            "address": address,
            "categories": [{"title": primary.replace("_", " ").title()}] if primary else [],
            "image_url": image_url,
            "url": place.get("googleMapsUri", ""),
            "coordinates": {
                "latitude": loc.get("latitude", 0),
                "longitude": loc.get("longitude", 0),
            },
            "location": {"display_address": [address]},
            "source": "google",
        }

    def get_reviews(self, place_id):
        if not self.api_key:
            return [], "Clé API Google Places manquante"

        try:
            headers = self._headers()
            headers["X-Goog-FieldMask"] = "reviews"

            r = requests.get(
                f"{self.base}/places/{place_id}",
                headers=headers,
                timeout=10,
            )
            if r.status_code != 200:
                return [], f"Erreur Google ({r.status_code})"

            data = r.json()
            reviews_raw = data.get("reviews", [])
            reviews = []
            for rev in reviews_raw[:3]:
                reviews.append({
                    "user": {"name": rev.get("authorAttribution", {}).get("displayName", "Anonyme")},
                    "text": rev.get("text", {}).get("text", "") if isinstance(rev.get("text"), dict) else rev.get("text", ""),
                    "rating": rev.get("rating", 0),
                })
            return reviews, None

        except Exception as e:
            return [], f"Erreur Google: {e}"


# Réutiliser les coords de yelp_client
from yelp_client import PARIS_ARRONDISSEMENT_COORDS