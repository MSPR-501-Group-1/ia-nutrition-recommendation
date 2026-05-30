#!/usr/bin/env python3
"""
Seed USDA SR Legacy dans la table ingredient de PostgreSQL.
Complète les données CIQUAL avec les aliments de base bruts manquants.

Prérequis :
  1. Dézipper le CSV SR Legacy dans scripts/sr-legacy/
     → food.csv, food_nutrient.csv, nutrient.csv, food_category.csv
  2. pip install pandas psycopg2-binary
  3. python scripts/seed_usda_sr_legacy.py

Ne touche PAS aux données CIQUAL existantes (pas de TRUNCATE).
Insère uniquement les aliments absents de la base.

Variables d'environnement (optionnel) :
  DB_HOST      localhost
  DB_PORT      5433
  DB_NAME      database
  DB_USER      admin
  DB_PASSWORD  secret
"""

import os
import sys
import uuid

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas manquant → pip install pandas")

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    sys.exit("psycopg2 manquant → pip install psycopg2-binary")

# ── Connexion DB ───────────────────────────────────────────────────────────────
DB = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5433")),
    "dbname":   os.getenv("DB_NAME",     "database"),
    "user":     os.getenv("DB_USER",     "admin"),
    "password": os.getenv("DB_PASSWORD", "secret"),
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SR_DIR     = os.path.join(SCRIPT_DIR, "SR_legacy")
BATCH_SIZE = 200

# ── IDs nutriments USDA → colonnes DB ─────────────────────────────────────────
# Valeurs toutes exprimées pour 100g dans SR Legacy
NUTRIENT_MAP = {
    1008: "calories_g",      # Energy (kcal/100g)
    1003: "protein_g",       # Protein (g/100g)
    1004: "fat_g",           # Total lipid / fat (g/100g)
    1005: "carbs_g",         # Carbohydrate, by difference (g/100g)
    1079: "fiber_g",         # Fiber, total dietary (g/100g)
    2000: "sugar_g",         # Sugars, total (g/100g)
    1093: "sodium_mg",       # Sodium (mg/100g)
    1253: "cholesterol_mg",  # Cholesterol (mg/100g)
}

# Plafonds physiologiques par colonne (valeur > max → NULL)
# Identiques à seed_ciqual.py pour cohérence
NUTRIENT_CAPS = {
    "calories_g":     900.0,
    "protein_g":      100.0,
    "fat_g":          100.0,
    "carbs_g":        100.0,
    "fiber_g":         80.0,
    "sugar_g":        100.0,
    "sodium_mg":      999.0,   # DECIMAL(5,2) → max 999.99 ; sel pur → NULL
    "cholesterol_mg": 999.0,   # DECIMAL(5,2) → max 999.99 ; jaune d'œuf pur → NULL
}

# ── Mapping catégories USDA → catégories DB ────────────────────────────────────
CATEGORY_MAP = {
    1:  "DAIRY",      # Dairy and Egg Products
    2:  "VEGETABLE",  # Spices and Herbs
    4:  "OTHER",      # Fats and Oils
    5:  "MEAT",       # Poultry Products
    8:  "GRAIN",      # Breakfast Cereals
    9:  "FRUIT",      # Fruits and Fruit Juices
    10: "MEAT",       # Pork Products
    11: "VEGETABLE",  # Vegetables and Vegetable Products
    12: "SNACK",      # Nut and Seed Products
    13: "MEAT",       # Beef Products
    14: "BEVERAGE",   # Beverages
    15: "MEAT",       # Finfish and Shellfish Products
    16: "VEGETABLE",  # Legumes and Legume Products
    17: "MEAT",       # Lamb, Veal, and Game Products
    18: "GRAIN",      # Baked Products
    19: "SNACK",      # Sweets
    20: "GRAIN",      # Cereal Grains and Pasta
    23: "SNACK",      # Snacks
    28: "BEVERAGE",   # Alcoholic Beverages
}

# Catégories exclues : plats préparés, fast-food, bébé, restauration, branded
EXCLUDED_CATEGORIES = {3, 6, 7, 21, 22, 24, 25, 26, 27}

# Mots-clés dans la description → produit trop transformé → ignoré
_SKIP_KW = {
    "baby food", "infant formula", "fast food", "mcdonald", "burger king",
    "subway", "pizza hut", "kfc", "taco bell", "wendy", "ready-to-serve",
    "restaurant", "commercial item", "quality control",
}

# ── Flags diététiques ──────────────────────────────────────────────────────────
_MEAT_KW: frozenset = frozenset({
    "chicken", "beef", "pork", "lamb", "turkey", "duck", "goose", "rabbit",
    "veal", "venison", "bison", "goat", "fish", "salmon", "tuna", "cod",
    "trout", "halibut", "tilapia", "catfish", "sardine", "anchovy", "herring",
    "mackerel", "shrimp", "crab", "lobster", "clam", "oyster", "mussel",
    "scallop", "squid", "octopus", "crayfish", "snail",
})

_DAIRY_KW: frozenset = frozenset({
    "milk", "cheese", "butter", "cream", "yogurt", "whey", "casein",
    "mozzarella", "parmesan", "cheddar", "brie", "feta", "ricotta",
    "gouda", "camembert", "lactose", "dairy",
})

_EGG_KW: frozenset = frozenset({"egg"})

_GLUTEN_KW: frozenset = frozenset({
    "wheat", "barley", "rye", "spelt", "kamut", "triticale", "gluten",
    "flour", "bread", "pasta", "semolina", "bulgur", "couscous",
    "biscuit", "cracker", "cake", "muffin", "waffle", "pancake",
    "pretzel", "cereal",
})

_GLUTEN_FREE_GRAINS: frozenset = frozenset({
    "rice", "corn", "maize", "quinoa", "buckwheat", "millet",
    "sorghum", "amaranth", "teff",
})


def _compute_flags(name: str, category: str) -> tuple[bool, bool, bool, bool]:
    n = name.lower()
    has_meat  = category == "MEAT"  or any(k in n for k in _MEAT_KW)
    has_dairy = category == "DAIRY" or any(k in n for k in _DAIRY_KW)
    has_egg   = any(k in n for k in _EGG_KW)
    if category == "GRAIN":
        has_gluten = not any(k in n for k in _GLUTEN_FREE_GRAINS)
    else:
        has_gluten = any(k in n for k in _GLUTEN_KW)
    return (
        not has_meat,
        not has_meat and not has_dairy and not has_egg,
        not has_gluten,
        not has_dairy,
    )


def _cap(val: float | None, max_val: float) -> float | None:
    if val is None:
        return None
    return val if val <= max_val else None


def _safe(row: "pd.Series", col: str) -> float | None:
    v = row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return _cap(float(v), NUTRIENT_CAPS[col])


def main():
    # ── Vérification des fichiers ──────────────────────────────────────────────
    required = ["food.csv", "food_nutrient.csv", "nutrient.csv", "food_category.csv"]
    for f in required:
        path = os.path.join(SR_DIR, f)
        if not os.path.exists(path):
            sys.exit(f"Fichier manquant : {path}\n"
                     "Dézippez SR Legacy dans scripts/sr-legacy/")

    # ── Chargement ────────────────────────────────────────────────────────────
    print("Chargement des fichiers SR Legacy...")
    food         = pd.read_csv(os.path.join(SR_DIR, "food.csv"),         dtype=str)
    food_nutrient= pd.read_csv(os.path.join(SR_DIR, "food_nutrient.csv"),dtype=str)
    print(f"  {len(food)} aliments bruts, {len(food_nutrient)} valeurs nutritionnelles")

    # ── Filtrage catégories ────────────────────────────────────────────────────
    food["food_category_id"] = pd.to_numeric(food["food_category_id"], errors="coerce")
    food = food[food["food_category_id"].isin(CATEGORY_MAP.keys())].copy()
    print(f"  {len(food)} aliments après filtrage catégories valides")

    # ── Exclusion produits trop transformés ───────────────────────────────────
    def _is_basic(desc: str) -> bool:
        d = desc.lower()
        return not any(kw in d for kw in _SKIP_KW)

    food = food[food["description"].apply(_is_basic)].copy()
    print(f"  {len(food)} aliments après exclusion produits transformés")

    # ── Pivot des nutriments : fdc_id → {colonne: valeur} ────────────────────
    fn = food_nutrient.copy()
    fn["nutrient_id"] = pd.to_numeric(fn["nutrient_id"], errors="coerce")
    fn["amount"]      = pd.to_numeric(fn["amount"],      errors="coerce")
    fn = fn[fn["nutrient_id"].isin(NUTRIENT_MAP.keys())][["fdc_id", "nutrient_id", "amount"]]
    fn["col"] = fn["nutrient_id"].map(NUTRIENT_MAP)

    pivot = fn.pivot_table(index="fdc_id", columns="col", values="amount", aggfunc="first")
    pivot = pivot.reset_index()
    pivot["fdc_id"] = pivot["fdc_id"].astype(str)
    food["fdc_id"]  = food["fdc_id"].astype(str)

    merged = food.merge(pivot, on="fdc_id", how="left")
    print(f"  {len(merged)} lignes après jointure nutritionnelle")

    # ── Connexion PostgreSQL ───────────────────────────────────────────────────
    print(f"Connexion → {DB['host']}:{DB['port']}/{DB['dbname']} ...")
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError as e:
        sys.exit(f"Connexion échouée : {e}")

    cur = conn.cursor()

    # Récupère noms et usda_names déjà en base pour éviter les doublons
    cur.execute("SELECT LOWER(name), LOWER(COALESCE(usda_name, '')) FROM ingredient")
    rows_existing = cur.fetchall()
    existing_names = {r[0] for r in rows_existing}
    existing_usda  = {r[1] for r in rows_existing if r[1]}

    # ── Construction des lignes à insérer ─────────────────────────────────────
    print("Construction des lignes...")
    rows_to_insert = []
    skipped_no_cal  = 0
    skipped_dup     = 0

    for _, row in merged.iterrows():
        description = str(row.get("description", "")).strip()
        if not description:
            continue

        # Skip doublons (par name ou usda_name)
        if description.lower() in existing_names or description.lower() in existing_usda:
            skipped_dup += 1
            continue

        # Skip si pas de calories
        cal = row.get("calories_g")
        if cal is None or (isinstance(cal, float) and pd.isna(cal)):
            skipped_no_cal += 1
            continue
        cal = float(cal)

        cat_id   = int(row.get("food_category_id", 0))
        category = CATEGORY_MAP.get(cat_id, "OTHER")
        flags    = _compute_flags(description, category)

        rows_to_insert.append((
            str(uuid.uuid4()),
            description[:255],        # name (EN — sert au matching HuggingFace)
            category,
            None,                     # nutriscore (non disponible USDA)
            _cap(cal, 900.0),         # calories_g
            _safe(row, "fat_g"),
            _safe(row, "fiber_g"),
            _safe(row, "sugar_g"),
            _safe(row, "sodium_mg"),
            _safe(row, "cholesterol_mg"),
            _safe(row, "protein_g"),
            _safe(row, "carbs_g"),
            description[:60],         # usda_name (nom EN pour matching)
            None,                     # price_per_kg
            *flags,
        ))

    print(f"  {len(rows_to_insert)} nouveaux ingrédients à insérer")
    print(f"  {skipped_dup} ignorés (déjà en base), {skipped_no_cal} ignorés (pas de calories)")

    # ── Insertion ─────────────────────────────────────────────────────────────
    INSERT_SQL = """
        INSERT INTO ingredient (
            ingredient_id, name, category, nutriscore,
            calories_g, fat_g, fiber_g, sugar_g, sodium_mg, cholesterol_mg,
            protein_g, carbs_g, usda_name, price_per_kg,
            is_vegetarian, is_vegan, is_gluten_free, is_dairy_free
        )
        VALUES (%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """

    if rows_to_insert:
        cur.execute("SELECT COUNT(*) FROM ingredient")
        before = cur.fetchone()[0]

        execute_batch(cur, INSERT_SQL, rows_to_insert, page_size=BATCH_SIZE)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM ingredient")
        after = cur.fetchone()[0]
        print(f"\nTerminé. Ingrédients : {before} → {after} (+{after - before})")
    else:
        print("\nAucun nouvel ingrédient à insérer.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
