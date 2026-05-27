# app/services/nutrition/pricing_service.py
# Prix de secours par catégorie — marché français 2025.
# Utilisé quand price_per_kg est absent ou nul en base.
# Mutualisé entre meal_plan_adapter et analyze_meal_service.

from typing import Optional

# ─── Dictionnaire de fallback ─────────────────────────────────────────────────

FALLBACK_PRICES_PER_KG: dict[str, float] = {
    "MEAT":      15.0,   # viandes, poissons, œufs
    "VEGETABLE":  3.0,   # légumes frais
    "FRUIT":      2.5,   # fruits frais
    "DAIRY":      4.0,   # lait, fromage, yaourt
    "GRAIN":      2.0,   # riz, pâtes, pain, céréales, légumineuses
    "BEVERAGE":   1.5,   # boissons
    "SNACK":      6.0,   # noix, barres, snacks
    "OTHER":      3.0,   # défaut
}

_DEFAULT_PRICE = 3.0

# Mots-clés pour deviner la catégorie des ingrédients non trouvés en DB
_KEYWORD_MAP: dict[str, str] = {
    # MEAT
    "chicken": "MEAT", "poulet": "MEAT", "beef": "MEAT", "bœuf": "MEAT",
    "boeuf": "MEAT", "porc": "MEAT", "pork": "MEAT", "salmon": "MEAT",
    "saumon": "MEAT", "thon": "MEAT", "tuna": "MEAT", "turkey": "MEAT",
    "dinde": "MEAT", "lamb": "MEAT", "agneau": "MEAT", "fish": "MEAT",
    "poisson": "MEAT", "crevette": "MEAT", "shrimp": "MEAT",
    "egg": "MEAT", "oeuf": "MEAT", "œuf": "MEAT", "jambon": "MEAT",
    "ham": "MEAT", "steak": "MEAT", "viande": "MEAT",
    # VEGETABLE
    "broccoli": "VEGETABLE", "brocoli": "VEGETABLE", "spinach": "VEGETABLE",
    "épinard": "VEGETABLE", "epinard": "VEGETABLE", "carrot": "VEGETABLE",
    "carotte": "VEGETABLE", "tomato": "VEGETABLE", "tomate": "VEGETABLE",
    "onion": "VEGETABLE", "oignon": "VEGETABLE", "pepper": "VEGETABLE",
    "poivron": "VEGETABLE", "zucchini": "VEGETABLE", "courgette": "VEGETABLE",
    "cucumber": "VEGETABLE", "concombre": "VEGETABLE", "lettuce": "VEGETABLE",
    "laitue": "VEGETABLE", "mushroom": "VEGETABLE", "champignon": "VEGETABLE",
    "garlic": "VEGETABLE", "ail": "VEGETABLE", "haricot": "VEGETABLE",
    "bean": "VEGETABLE", "pois": "VEGETABLE", "pea": "VEGETABLE",
    "aubergine": "VEGETABLE", "eggplant": "VEGETABLE", "chou": "VEGETABLE",
    "cabbage": "VEGETABLE", "leek": "VEGETABLE", "poireau": "VEGETABLE",
    # FRUIT
    "banana": "FRUIT", "banane": "FRUIT", "apple": "FRUIT", "pomme": "FRUIT",
    "orange": "FRUIT", "strawberry": "FRUIT", "fraise": "FRUIT",
    "blueberry": "FRUIT", "myrtille": "FRUIT", "mango": "FRUIT",
    "mangue": "FRUIT", "avocado": "FRUIT", "avocat": "FRUIT",
    "pear": "FRUIT", "poire": "FRUIT", "peach": "FRUIT", "pêche": "FRUIT",
    "grape": "FRUIT", "raisin": "FRUIT", "kiwi": "FRUIT", "citron": "FRUIT",
    "lemon": "FRUIT",
    # DAIRY
    "milk": "DAIRY", "lait": "DAIRY", "cheese": "DAIRY", "fromage": "DAIRY",
    "yogurt": "DAIRY", "yaourt": "DAIRY", "yoghurt": "DAIRY",
    "butter": "DAIRY", "beurre": "DAIRY", "cream": "DAIRY",
    "crème": "DAIRY", "creme": "DAIRY", "quark": "DAIRY",
    "mozzarella": "DAIRY", "parmesan": "DAIRY",
    # GRAIN
    "rice": "GRAIN", "riz": "GRAIN", "pasta": "GRAIN", "pâtes": "GRAIN",
    "pates": "GRAIN", "bread": "GRAIN", "pain": "GRAIN", "oat": "GRAIN",
    "avoine": "GRAIN", "quinoa": "GRAIN", "flour": "GRAIN", "farine": "GRAIN",
    "lentil": "GRAIN", "lentille": "GRAIN", "chickpea": "GRAIN",
    "pois chiche": "GRAIN", "cereal": "GRAIN", "céréale": "GRAIN",
    "couscous": "GRAIN", "boulgour": "GRAIN", "bulgur": "GRAIN",
    "tortilla": "GRAIN", "granola": "GRAIN",
    # BEVERAGE
    "juice": "BEVERAGE", "jus": "BEVERAGE", "water": "BEVERAGE",
    "eau": "BEVERAGE", "tea": "BEVERAGE", "thé": "BEVERAGE",
    "coffee": "BEVERAGE", "café": "BEVERAGE", "smoothie": "BEVERAGE",
    # SNACK
    "chocolate": "SNACK", "chocolat": "SNACK", "nut": "SNACK",
    "noix": "SNACK", "almond": "SNACK", "amande": "SNACK",
    "cashew": "SNACK", "peanut": "SNACK", "cacahuète": "SNACK",
    "cacahuete": "SNACK", "noisette": "SNACK", "hazelnut": "SNACK",
}


# ─── Fonctions utilitaires ─────────────────────────────────────────────────────

def guess_category_from_name(name: str) -> str:
    """Devine la catégorie d'un ingrédient non trouvé en DB à partir de son nom."""
    name_lower = name.lower()
    for keyword, category in _KEYWORD_MAP.items():
        if keyword in name_lower:
            return category
    return "OTHER"


def get_price_per_kg(category: str, db_price: Optional[float] = None) -> float:
    """
    Retourne le prix au kg à utiliser.
    Priorité : prix DB (si > 0) → fallback par catégorie → défaut 3 €/kg.
    """
    if db_price and float(db_price) > 0:
        return float(db_price)
    return FALLBACK_PRICES_PER_KG.get((category or "OTHER").upper(), _DEFAULT_PRICE)


def compute_ingredient_cost(
    category: str,
    quantity_g: float,
    db_price: Optional[float] = None,
) -> float:
    """Calcule le coût en euros d'un ingrédient pour la quantité donnée."""
    price = get_price_per_kg(category, db_price)
    return round(price * quantity_g / 1000.0, 3)
