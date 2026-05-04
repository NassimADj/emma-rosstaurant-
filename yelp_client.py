import requests
from config import YELP_BASE_URL, MAX_RESULTS, PARIS_ARRONDISSEMENTS, get_secret


class YelpClient:
    def __init__(self):
        self._key = None
        self.base = YELP_BASE_URL

    @property
    def api_key(self):
        if self._key is None:
            self._key = get_secret("YELP_API_KEY")
        return self._key

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def available(self):
        return bool(self.api_key)

    def _get(self, endpoint, params):
        if not self.api_key:
            return None, "Clé API Yelp manquante — ajoute-la dans .env"
        try:
            r = requests.get(
                f"{self.base}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            if r.status_code == 401:
                return None, "Clé API Yelp invalide — vérifie ton .env"
            if r.status_code == 429:
                return None, "Limite d'appels Yelp atteinte — réessaie dans 1h"
            if r.status_code != 200:
                return None, f"Erreur Yelp ({r.status_code})"
            return r.json(), None
        except requests.Timeout:
            return None, "Yelp ne répond pas — réessaie dans quelques secondes"
        except requests.ConnectionError:
            return None, "Pas de connexion internet"

    def search(self, arrondissement=None, term=None, categories=None,
               price=None, limit=MAX_RESULTS, sort_by="rating", offset=0):
        params = {
            "limit": limit,
            "sort_by": sort_by,
            "offset": offset,
        }
        if price:
            params["price"] = price
        if categories:
            params["categories"] = categories
        if term:
            params["term"] = term

        if arrondissement and arrondissement in PARIS_ARRONDISSEMENT_COORDS:
            coords = PARIS_ARRONDISSEMENT_COORDS[arrondissement]
            params["latitude"] = coords["lat"]
            params["longitude"] = coords["lon"]
            params["radius"] = 4000
        else:
            # Tout Paris
            params["latitude"] = 48.8566
            params["longitude"] = 2.3522
            params["radius"] = 5000

        data, err = self._get("businesses/search", params)
        if err:
            return [], err, 0

        businesses = data.get("businesses", [])

        # Filtrer les résultats hors arrondissement par code postal
        if arrondissement and arrondissement in PARIS_ARRONDISSEMENTS:
            expected_zip = PARIS_ARRONDISSEMENTS[arrondissement]
            businesses = [
                b for b in businesses
                if expected_zip in b.get("location", {}).get("zip_code", "")
            ]

        return businesses, None, data.get("total", 0)

    def get_details(self, business_id):
        data, err = self._get(f"businesses/{business_id}", {})
        if err:
            return None, err
        return data, None

    def get_reviews(self, business_id):
        data, err = self._get(f"businesses/{business_id}/reviews", {})
        if err:
            return [], err
        return data.get("reviews", []), None


# Coordonnées centre de chaque arrondissement parisien
PARIS_ARRONDISSEMENT_COORDS = {
    "1er":  {"lat": 48.8606, "lon": 2.3376},
    "2e":   {"lat": 48.8689, "lon": 2.3411},
    "3e":   {"lat": 48.8627, "lon": 2.3602},
    "4e":   {"lat": 48.8545, "lon": 2.3570},
    "5e":   {"lat": 48.8444, "lon": 2.3510},
    "6e":   {"lat": 48.8500, "lon": 2.3320},
    "7e":   {"lat": 48.8560, "lon": 2.3080},
    "8e":   {"lat": 48.8730, "lon": 2.3180},
    "9e":   {"lat": 48.8780, "lon": 2.3390},
    "10e":  {"lat": 48.8740, "lon": 2.3600},
    "11e":  {"lat": 48.8620, "lon": 2.3800},
    "12e":  {"lat": 48.8400, "lon": 2.3890},
    "13e":  {"lat": 48.8320, "lon": 2.3560},
    "14e":  {"lat": 48.8280, "lon": 2.3260},
    "15e":  {"lat": 48.8410, "lon": 2.2980},
    "16e":  {"lat": 48.8620, "lon": 2.2780},
    "17e":  {"lat": 48.8840, "lon": 2.3080},
    "18e":  {"lat": 48.8880, "lon": 2.3440},
    "19e":  {"lat": 48.8850, "lon": 2.3820},
    "20e":  {"lat": 48.8670, "lon": 2.3990},
}