#!/usr/bin/env python3
"""
Seed Ciqual 2020 dans la table ingredient de PostgreSQL.

Instructions :
  1. Téléchargez Ciqual 2020 sur https://ciqual.anses.fr/
     → Fichier Excel "Table Ciqual 2020_FR_2020 07 07.xls" (ou .xlsx)
  2. Renommez-le 'ciqual.xls' et placez-le dans ce dossier (scripts/)
  3. Installez les dépendances : pip install pandas openpyxl xlrd psycopg2-binary
  4. Lancez : python scripts/seed_ciqual.py

Variables d'environnement (facultatif) :
  DB_HOST      localhost
  DB_PORT      5433
  DB_NAME      database   ← nom de votre base PostgreSQL
  DB_USER      admin
  DB_PASSWORD  secret
"""

import os
import re
import sys
import uuid

# ── Dépendances ────────────────────────────────────────────────────────────────
try:
    import pandas as pd
except ImportError:
    sys.exit("pandas manquant → pip install pandas openpyxl xlrd")

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

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
BATCH_SIZE  = 200

# Accepte n'importe quel .csv / .xls / .xlsx dans le dossier scripts/
CIQUAL_FILE = next(
    (os.path.join(SCRIPT_DIR, f) for f in os.listdir(SCRIPT_DIR)
     if f.lower().endswith((".csv", ".xls", ".xlsx")) and f != "seed_ciqual.py"),
    None,
)

# ── Mapping groupes + sous-groupes Ciqual → catégories DB ──────────────────────
# Couvre alim_grp_nom_fr ET alim_ssgrp_nom_fr + alim_ssssgrp_nom_fr
# Ordre : du plus spécifique au plus général
_GROUP_MAP: list[tuple[str, str]] = [
    # ── MEAT : viandes, poissons, œufs ────────────────────────────────────────
    ("charcuterie",          "MEAT"),
    ("abat",                 "MEAT"),
    ("abats",                "MEAT"),
    ("bœuf",                 "MEAT"),
    ("boeuf",                "MEAT"),
    ("veau",                 "MEAT"),
    ("porc",                 "MEAT"),
    ("agneau",               "MEAT"),
    ("mouton",               "MEAT"),
    ("cheval",               "MEAT"),
    ("lapin",                "MEAT"),
    ("canard",               "MEAT"),
    ("oie",                  "MEAT"),
    ("dinde",                "MEAT"),
    ("poulet",               "MEAT"),
    ("volaille",             "MEAT"),
    ("gibier",               "MEAT"),
    ("viande",               "MEAT"),
    ("jambon",               "MEAT"),
    ("saucisse",             "MEAT"),
    ("saucisson",            "MEAT"),
    ("lardons",              "MEAT"),
    ("bacon",                "MEAT"),
    ("merguez",              "MEAT"),
    ("saumon",               "MEAT"),
    ("thon",                 "MEAT"),
    ("sardine",              "MEAT"),
    ("maquereau",            "MEAT"),
    ("cabillaud",            "MEAT"),
    ("truite",               "MEAT"),
    ("colin",                "MEAT"),
    ("sole",                 "MEAT"),
    ("daurade",              "MEAT"),
    ("poisson",              "MEAT"),
    ("crustacé",             "MEAT"),
    ("crevette",             "MEAT"),
    ("homard",               "MEAT"),
    ("crabe",                "MEAT"),
    ("langoustine",          "MEAT"),
    ("mollusque",            "MEAT"),
    ("moule",                "MEAT"),
    ("huître",               "MEAT"),
    ("palourde",             "MEAT"),
    ("coquillage",           "MEAT"),
    ("céphalopode",          "MEAT"),
    ("calmar",               "MEAT"),
    ("pieuvre",              "MEAT"),
    ("produit de la pêche",  "MEAT"),
    ("oeuf",                 "MEAT"),
    ("œuf",                  "MEAT"),
    # ── DAIRY : produits laitiers ─────────────────────────────────────────────
    ("fromage",              "DAIRY"),
    ("yaourt",               "DAIRY"),
    ("yogourt",              "DAIRY"),
    ("lait fermenté",        "DAIRY"),
    ("lait",                 "DAIRY"),
    ("beurre",               "DAIRY"),
    ("crème fraîche",        "DAIRY"),
    ("crème de lait",        "DAIRY"),
    ("dessert lacté",        "DAIRY"),
    ("glace et crème glacée","DAIRY"),
    ("entremets",            "DAIRY"),
    ("faisselle",            "DAIRY"),
    ("produit laitier",      "DAIRY"),
    ("lacté",                "DAIRY"),
    # ── VEGETABLE : légumes, légumineuses, aromatiques ─────────────────────────
    ("légumineuse",          "VEGETABLE"),
    ("lentille",             "VEGETABLE"),
    ("pois chiche",          "VEGETABLE"),
    ("haricot",              "VEGETABLE"),
    ("fève",                 "VEGETABLE"),
    ("légume",               "VEGETABLE"),
    ("plante aromatique",    "VEGETABLE"),
    ("aromate",              "VEGETABLE"),
    ("herbe aromatique",     "VEGETABLE"),
    ("épice",                "VEGETABLE"),
    ("champignon",           "VEGETABLE"),
    ("algue",                "VEGETABLE"),
    ("pomme de terre",       "VEGETABLE"),
    ("tubercule",            "VEGETABLE"),
    # ── FRUIT ─────────────────────────────────────────────────────────────────
    ("fruit",                "FRUIT"),
    ("baie",                 "FRUIT"),
    ("agrume",               "FRUIT"),
    ("melon",                "FRUIT"),
    ("pastèque",             "FRUIT"),
    ("raisin",               "FRUIT"),
    ("fraise",               "FRUIT"),
    ("cerise",               "FRUIT"),
    ("pêche",                "FRUIT"),
    ("abricot",              "FRUIT"),
    ("prune",                "FRUIT"),
    ("ananas",               "FRUIT"),
    ("mangue",               "FRUIT"),
    ("avocat",               "FRUIT"),
    ("olive",                "FRUIT"),
    # ── GRAIN : céréales, pains, pâtes ────────────────────────────────────────
    ("céréale",              "GRAIN"),
    ("produit céréalier",    "GRAIN"),
    ("biscottes",            "GRAIN"),
    ("biscotte",             "GRAIN"),
    ("pain",                 "GRAIN"),
    ("baguette",             "GRAIN"),
    ("brioche",              "GRAIN"),
    ("viennoiserie",         "GRAIN"),
    ("pâte alimentaire",     "GRAIN"),
    ("macaroni",             "GRAIN"),
    ("spaghetti",            "GRAIN"),
    ("tagliatelle",          "GRAIN"),
    ("pâtes",                "GRAIN"),
    ("farine",               "GRAIN"),
    ("semoule",              "GRAIN"),
    ("couscous",             "GRAIN"),
    ("quinoa",               "GRAIN"),
    ("riz",                  "GRAIN"),
    ("avoine",               "GRAIN"),
    ("flocon",               "GRAIN"),
    ("blé",                  "GRAIN"),
    ("orge",                 "GRAIN"),
    ("seigle",               "GRAIN"),
    ("maïs",                 "GRAIN"),
    ("millet",               "GRAIN"),
    ("épeautre",             "GRAIN"),
    ("sarrasin",             "GRAIN"),
    # ── BEVERAGE : boissons avec et sans alcool ────────────────────────────────
    ("boisson",              "BEVERAGE"),
    ("eau",                  "BEVERAGE"),
    ("jus de fruit",         "BEVERAGE"),
    ("nectar",               "BEVERAGE"),
    ("soda",                 "BEVERAGE"),
    ("cola",                 "BEVERAGE"),
    ("limonade",             "BEVERAGE"),
    ("café",                 "BEVERAGE"),
    ("thé",                  "BEVERAGE"),
    ("infusion",             "BEVERAGE"),
    ("tisane",               "BEVERAGE"),
    ("lait végétal",         "BEVERAGE"),
    ("bière",                "BEVERAGE"),
    ("vin",                  "BEVERAGE"),
    ("cidre",                "BEVERAGE"),
    ("champagne",            "BEVERAGE"),
    ("spiritueux",           "BEVERAGE"),
    ("alcool",               "BEVERAGE"),
    ("sirop",                "BEVERAGE"),
    ("smoothie",             "BEVERAGE"),
    # ── SNACK : noix, sucreries, biscuits, condiments ─────────────────────────
    ("amande",               "SNACK"),
    ("noisette",             "SNACK"),
    ("noix de cajou",        "SNACK"),
    ("pistache",             "SNACK"),
    ("cacahuète",            "SNACK"),
    ("cacahuete",            "SNACK"),
    ("noix de coco",         "SNACK"),
    ("noix",                 "SNACK"),
    ("graine oléag",         "SNACK"),
    ("oléagineux",           "SNACK"),
    ("graine de",            "SNACK"),
    ("chocolat",             "SNACK"),
    ("cacao",                "SNACK"),
    ("confiserie",           "SNACK"),
    ("bonbon",               "SNACK"),
    ("caramel",              "SNACK"),
    ("confiture",            "SNACK"),
    ("gelée de fruit",       "SNACK"),
    ("miel",                 "SNACK"),
    ("pâte à tartiner",      "SNACK"),
    ("produit sucré",        "SNACK"),
    ("sucre",                "SNACK"),
    ("biscuit",              "SNACK"),
    ("gâteau",               "SNACK"),
    ("tarte",                "SNACK"),
    ("pâtisserie",           "SNACK"),
    ("chips",                "SNACK"),
    ("snack",                "SNACK"),
    ("apéritif",             "SNACK"),
    ("dessert",              "SNACK"),
    ("crème dessert",        "SNACK"),
]


def _category(grp: str, ssgrp: str = "", ssssgrp: str = "") -> str:
    """
    Cherche dans le groupe principal, le sous-groupe et le sous-sous-groupe.
    Retourne la première catégorie trouvée, sinon 'OTHER'.
    """
    combined = f"{grp} {ssgrp} {ssssgrp}".lower()
    for keyword, cat in _GROUP_MAP:
        if keyword in combined:
            return cat
    return "OTHER"


# ── Parsing valeurs Ciqual ─────────────────────────────────────────────────────
# Ciqual utilise : "-" (absence), "traces" (~0), "<0.05" (limite détection)
def _parse(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", ".")
    if s in ("-", "", "nan", "NaN", "nd", "NC"):
        return None
    if s.lower() == "traces":
        return 0.001
    m = re.match(r"^[<>]?\s*([\d.]+)", s)
    if m:
        v = float(m.group(1))
        return v
    return None


def _cap(val: float | None, max_val: float) -> float | None:
    """Plafonne la valeur aux limites de la colonne DB pour éviter l'overflow."""
    if val is None:
        return None
    return min(val, max_val)


# ── Détection automatique des colonnes ─────────────────────────────────────────
def _find_col(df: "pd.DataFrame", *patterns: str) -> str | None:
    for col in df.columns:
        col_lower = col.lower()
        if all(p.lower() in col_lower for p in patterns):
            return col
    # Tolérance : un seul pattern suffit
    for col in df.columns:
        col_lower = col.lower()
        for p in patterns:
            if p.lower() in col_lower:
                return col
    return None


def _load_ciqual(path: str) -> "pd.DataFrame":
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".xls":
            return pd.read_excel(path, engine="xlrd", header=0, dtype=str)
        return pd.read_excel(path, engine="openpyxl", header=0, dtype=str)
    except Exception as e:
        sys.exit(f"Impossible de lire {path} : {e}\n"
                 "Vérifiez que xlrd (pour .xls) ou openpyxl (pour .xlsx) est installé.")


def build_rows(df: "pd.DataFrame") -> list[tuple]:
    col_name    = _find_col(df, "alim_nom_fr") or _find_col(df, "nom_fr") or _find_col(df, "nom")
    col_grp     = _find_col(df, "alim_grp_nom_fr") or _find_col(df, "grp_nom") or _find_col(df, "groupe")
    col_ssgrp   = _find_col(df, "alim_ssgrp_nom_fr") or _find_col(df, "ssgrp_nom")
    col_ssssgrp = _find_col(df, "alim_ssssgrp_nom_fr") or _find_col(df, "ssssgrp_nom")
    col_cal     = _find_col(df, "kcal") or _find_col(df, "energie", "jones")
    col_prot    = _find_col(df, "protéine") or _find_col(df, "protein")
    col_carb    = _find_col(df, "glucide") or _find_col(df, "carb")
    col_fat     = _find_col(df, "lipide") or _find_col(df, "fat")
    col_fiber   = _find_col(df, "fibre") or _find_col(df, "fiber")
    col_sugar   = _find_col(df, "sucre") or _find_col(df, "sugar")
    col_sodium  = _find_col(df, "sodium")
    col_chol    = _find_col(df, "cholest")

    if not col_name:
        print("Colonnes disponibles :")
        for c in df.columns:
            print(f"  {c!r}")
        sys.exit("Colonne 'nom' introuvable — vérifiez le fichier Ciqual.")

    print(f"  nom            : {col_name}")
    print(f"  groupe         : {col_grp}")
    print(f"  sous-groupe    : {col_ssgrp}")
    print(f"  sous-sous-grp  : {col_ssssgrp}")
    print(f"  calories       : {col_cal}")
    print(f"  protéines      : {col_prot}")
    print(f"  glucides       : {col_carb}")
    print(f"  lipides        : {col_fat}")
    print(f"  fibres         : {col_fiber}")
    print(f"  sucres         : {col_sugar}")
    print(f"  sodium         : {col_sodium}")
    print(f"  cholestérol    : {col_chol}")

    rows = []
    skipped_no_cal = 0
    for _, row in df.iterrows():
        name = str(row.get(col_name, "")).strip()
        if not name or name.lower() in ("nan", ""):
            continue

        grp     = str(row.get(col_grp,     "")) if col_grp     else ""
        ssgrp   = str(row.get(col_ssgrp,   "")) if col_ssgrp   else ""
        ssssgrp = str(row.get(col_ssssgrp, "")) if col_ssssgrp else ""

        cal = _parse(row.get(col_cal))
        if cal is None:
            skipped_no_cal += 1
            continue

        rows.append((
            str(uuid.uuid4()),                  # ingredient_id
            name[:255],                          # name
            _category(grp, ssgrp, ssssgrp),                       # category (enum DB)
            None,                                                  # nutriscore (absent de Ciqual)
            _cap(cal, 999.9),                                      # calories_g  DECIMAL(4,1)
            _cap(_parse(row.get(col_fat))   if col_fat   else None, 999.9),   # fat_g
            _cap(_parse(row.get(col_fiber)) if col_fiber else None, 999.99),  # fiber_g
            _cap(_parse(row.get(col_sugar)) if col_sugar else None, 999.99),  # sugar_g
            _cap(_parse(row.get(col_sodium))if col_sodium else None, 999.99), # sodium_mg
            _cap(_parse(row.get(col_chol)) if col_chol  else None, 999.99),  # cholesterol_mg
            _cap(_parse(row.get(col_prot))  if col_prot  else None, 999.99),  # protein_g
            _cap(_parse(row.get(col_carb))  if col_carb  else None, 999.99),  # carbs_g
            None,                                                  # usda_name
            None,                                                  # price_per_kg
        ))
    print(f"  {len(rows)} ingrédients avec calories valides ({skipped_no_cal} ignorés sans calories).")
    return rows


INSERT_SQL = """
    INSERT INTO ingredient (
        ingredient_id, name, category, nutriscore,
        calories_g, fat_g, fiber_g, sugar_g, sodium_mg, cholesterol_mg,
        protein_g, carbs_g, usda_name, price_per_kg
    )
    VALUES (%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s,%s)
    ON CONFLICT DO NOTHING
"""


def main():
    if not CIQUAL_FILE:
        sys.exit(
            "Fichier Ciqual introuvable dans scripts/\n"
            "  → Téléchargez depuis https://ciqual.anses.fr/\n"
            "  → Renommez en 'ciqual.xls' ou 'ciqual.xlsx'\n"
            "  → Placez dans le dossier scripts/"
        )

    print(f"Chargement de {CIQUAL_FILE} ...")
    df = _load_ciqual(CIQUAL_FILE)
    print(f"  {len(df)} lignes dans le fichier.")

    print("Détection des colonnes ...")
    rows = build_rows(df)

    print(f"Connexion PostgreSQL → {DB['host']}:{DB['port']}/{DB['dbname']} ...")
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError as e:
        sys.exit(f"Connexion échouée : {e}\n"
                 "Vérifiez DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.")

    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM ingredient")
        before = cur.fetchone()[0]
        print(f"  Ingrédients existants : {before}")

        # Récupère les noms existants pour éviter les doublons
        cur.execute("SELECT LOWER(name) FROM ingredient")
        existing = {r[0] for r in cur.fetchall()}
        rows_new = [r for r in rows if r[1].lower() not in existing]
        print(f"  Nouveaux ingrédients à insérer : {len(rows_new)}")

        if rows_new:
            execute_batch(cur, INSERT_SQL, rows_new, page_size=BATCH_SIZE)
            conn.commit()

        cur.execute("SELECT COUNT(*) FROM ingredient")
        after = cur.fetchone()[0]
        print(f"\nTerminé. Ingrédients : {before} → {after} (+{after - before})")

    except Exception as e:
        conn.rollback()
        print(f"Erreur lors de l'insertion : {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
