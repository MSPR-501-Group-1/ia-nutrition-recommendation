# app/db/queries.py
# Toutes les requetes SQL sur le schema PostgreSQL de l ETL.
# Tables utilisees : ingredient, user_, health_goal, user_health_goal, user_metrics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_ingredient_by_name(db: AsyncSession, name: str) -> dict | None:
    """
    Cherche un ingrédient par nom (correspondance partielle).
    Filtre les lignes avec des données nutritionnelles aberrantes :
      - calories absentes, nulles ou > 900 kcal/100 g
      - fat_g > 95 g/100 g (physiquement impossible)
    Préfère la correspondance exacte.
    """
    result = await db.execute(
        text("""
            SELECT ingredient_id, name, calories_g, protein_g, carbs_g,
                   fat_g, fiber_g, sugar_g, sodium_mg, cholesterol_mg,
                   nutriscore, category, usda_name, price_per_kg
            FROM ingredient
            WHERE LOWER(name) LIKE LOWER(:pattern)
              AND COALESCE(calories_g, 0) BETWEEN 10 AND 900
              AND COALESCE(fat_g, 0) <= 95
            ORDER BY
                CASE WHEN LOWER(name) = LOWER(:exact) THEN 0 ELSE 1 END
            LIMIT 1
        """),
        {"pattern": f"%{name}%", "exact": name},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def search_ingredients(db: AsyncSession, name: str, limit: int = 10) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT ingredient_id, name, calories_g, protein_g, carbs_g,
                   fat_g, fiber_g, sugar_g, sodium_mg, cholesterol_mg,
                   nutriscore, category, usda_name, price_per_kg
            FROM ingredient
            WHERE LOWER(name) LIKE LOWER(:pattern)
            ORDER BY name
            LIMIT :limit
        """),
        {"pattern": f"%{name}%", "limit": limit},
    )
    return [dict(row) for row in result.mappings()]


async def get_ingredients_for_meal_plan(
    db: AsyncSession,
    diet_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    base_query = """
        SELECT ingredient_id, name, calories_g, protein_g, carbs_g,
               fat_g, fiber_g, nutriscore, category
        FROM ingredient
        WHERE 1=1
    """
    params: dict = {"limit": limit}

    if diet_type in ("vegan", "vegetarian"):
        base_query += " AND LOWER(category) NOT IN ('meat', 'fish', 'seafood')"
    if diet_type == "vegan":
        base_query += " AND LOWER(category) NOT IN ('dairy', 'eggs')"

    base_query += " ORDER BY RANDOM() LIMIT :limit"

    result = await db.execute(text(base_query), params)
    return [dict(row) for row in result.mappings()]


async def get_user_budget(db: AsyncSession, user_id: str) -> float | None:
    """Retourne budget_max_per_meal depuis user_preference, ou None si absent."""
    result = await db.execute(
        text("SELECT budget_max_per_meal FROM user_preference WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if row and row["budget_max_per_meal"] is not None:
        return float(row["budget_max_per_meal"])
    return None


async def save_meal_to_postgres(
    db: AsyncSession,
    user_id: str,
    calories: int,
    meal_totals: dict,
) -> None:
    """
    Trace légère d'un repas analysé dans la table `meal`.
    Non bloquant — l'appelant avale l'exception si elle survient.
    """
    await db.execute(
        text("""
            INSERT INTO meal (user_id, calories, protein_g, carbs_g, fat_g, fiber_g, analyzed_at)
            VALUES (:user_id, :calories, :protein_g, :carbs_g, :fat_g, :fiber_g, NOW())
            ON CONFLICT DO NOTHING
        """),
        {
            "user_id":   user_id,
            "calories":  calories,
            "protein_g": meal_totals.get("protein_g", 0),
            "carbs_g":   meal_totals.get("carbs_g",   0),
            "fat_g":     meal_totals.get("fat_g",     0),
            "fiber_g":   meal_totals.get("fiber_g",   0),
        },
    )
    await db.commit()


async def get_user_profile(db: AsyncSession, user_id: str) -> dict | None:
    result = await db.execute(
        text("""
            SELECT
                u.user_id,
                u.first_name,
                u.last_name,
                u.birth_date,
                u.gender_code,
                u.height_cm,
                u.current_weight_kg,
                u.diet_type,
                u.allergies,
                hg.label        AS goal_label,
                hg.description  AS goal_description
            FROM user_ u
            LEFT JOIN user_health_goal uhg ON u.user_id = uhg.user_id
            LEFT JOIN health_goal hg       ON uhg.goal_id = hg.goal_id
            WHERE u.user_id = :user_id
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    if not row:
        return None

    user = dict(row)

    metrics_result = await db.execute(
        text("""
            SELECT weight_kg, body_fat_percentage, bmi, resting_bpm, health_goal, fitness_level
            FROM user_metrics
            WHERE user_id = :user_id
            ORDER BY recorded_at DESC
            LIMIT 1
        """),
        {"user_id": user_id},
    )
    metrics_row = metrics_result.mappings().first()
    if metrics_row:
        user["latest_metrics"] = dict(metrics_row)
        if metrics_row["weight_kg"]:
            user["current_weight_kg"] = float(metrics_row["weight_kg"])

    return user
