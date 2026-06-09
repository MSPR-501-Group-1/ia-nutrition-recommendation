
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
from datetime import datetime, timezone

# ==========================================
# 1. REQUÊTES SUR LES INGRÉDIENTS (VISION IA)
# ==========================================

async def get_food_by_name(db: AsyncSession, name: str) -> dict | None:
    """
    Recherche un ingrédient dans la base PostgreSQL (ETL) à partir d'un label 
    détecté par Hugging Face ou Google Vision.
    """
    query = text("""
        SELECT ingredient_id, name, calories_g, protein_g, carbs_g, fat_g, fiber_g 
        FROM ingredient
        WHERE name ILIKE :search OR usda_name ILIKE :search
        LIMIT 1
    """)
    
    result = await db.execute(query, {"search": f"%{name}%"})
    row = result.fetchone()
    
    if row:
        return {
            "ingredient_id": row.ingredient_id,
            "name": row.name,
            "calories": float(row.calories_g) if row.calories_g else 0.0,
            "proteins": float(row.protein_g) if row.protein_g else 0.0,
            "carbs": float(row.carbs_g) if row.carbs_g else 0.0,
            "fats": float(row.fat_g) if row.fat_g else 0.0,
            "fibers": float(row.fiber_g) if row.fiber_g else 0.0
        }
    return None


async def get_ingredient_by_name(db: AsyncSession, name: str) -> dict | None:
    """
    Recherche un ingrédient dans PostgreSQL — clés normalisées (_g suffix)
    compatibles avec IngredientMatch et AnalyzeMealResponse.
    Utilisé par vision_orchestrator et la route /analyze-meal.
    """
    query = text("""
        SELECT ingredient_id, name, category, nutriscore,
               calories_g, protein_g, carbs_g, fat_g, fiber_g
        FROM ingredient
        WHERE name ILIKE :search OR usda_name ILIKE :search
        LIMIT 1
    """)

    result = await db.execute(query, {"search": f"%{name}%"})
    row = result.fetchone()

    if row:
        return {
            "ingredient_id": row.ingredient_id,
            "name":          row.name,
            "category":      str(row.category)   if row.category   else "OTHER",
            "nutriscore":    str(row.nutriscore)  if row.nutriscore else None,
            "calories_g":    float(row.calories_g) if row.calories_g else 0.0,
            "protein_g":     float(row.protein_g)  if row.protein_g  else 0.0,
            "carbs_g":       float(row.carbs_g)    if row.carbs_g    else 0.0,
            "fat_g":         float(row.fat_g)      if row.fat_g      else 0.0,
            "fiber_g":       float(row.fiber_g)    if row.fiber_g    else 0.0,
        }
    return None


async def search_ingredients(db: AsyncSession, query_str: str, limit: int = 10) -> list[dict]:
    """
    Recherche multi-résultats dans la table ingredient.
    Utilisé par GET /api/v1/ingredients/search.
    """
    query = text("""
        SELECT ingredient_id, name, category, nutriscore,
               calories_g, protein_g, carbs_g, fat_g, fiber_g
        FROM ingredient
        WHERE name ILIKE :search OR usda_name ILIKE :search
        ORDER BY name
        LIMIT :limit
    """)
    result = await db.execute(query, {"search": f"%{query_str}%", "limit": limit})
    return [
        {
            "ingredient_id": row.ingredient_id,
            "name":          row.name,
            "category":      str(row.category)    if row.category    else None,
            "nutriscore":    str(row.nutriscore)   if row.nutriscore  else None,
            "calories_g":    float(row.calories_g) if row.calories_g  else 0.0,
            "protein_g":     float(row.protein_g)  if row.protein_g   else 0.0,
            "carbs_g":       float(row.carbs_g)    if row.carbs_g     else 0.0,
            "fat_g":         float(row.fat_g)      if row.fat_g       else 0.0,
            "fiber_g":       float(row.fiber_g)    if row.fiber_g     else 0.0,
        }
        for row in result.fetchall()
    ]


async def get_foods_filtered_by_constraints(db: AsyncSession, user_profile: dict, limit: int = 30) -> list[dict]:
    """
    Récupère une liste d'ingrédients sûrs pour la génération NLP (Ollama).
    Prend en compte les allergies (simplifié ici).
    """
    allergies = user_profile.get("allergies")
    
    # Si l'utilisateur est allergique, on exclut le terme de la recherche
    allergy_filter = "AND name NOT ILIKE :allergy AND category != :allergy" if allergies else ""
    
    query = text(f"""
        SELECT name, calories_g, protein_g, carbs_g, fat_g, category
        FROM ingredient
        WHERE 1=1 {allergy_filter}
        ORDER BY RANDOM()
        LIMIT :limit
    """)
    
    params: dict = {"limit": limit}
    if allergies:
        params["allergy"] = f"%{allergies}%"
        
    result = await db.execute(query, params)
    
    return [
        {
            "name": row.name,
            "category": row.category,
            "macros": f"{row.calories_g}kcal, {row.protein_g}g prot"
        } 
        for row in result.fetchall()
    ]


# ==========================================
# 2. REQUÊTES SUR LE PROFIL UTILISATEUR
# ==========================================

async def get_user_profile(db: AsyncSession, user_id: str) -> dict | None:
    """
    Récupère le profil complet de l'utilisateur avec son objectif de santé.
    """
    query = text("""
        SELECT u.user_id, u.first_name, u.email, u.allergies, u.diet_type,
               u.height_cm, u.current_weight_kg, u.gender_code, u.birth_date,
               g.label AS goal_label, g.description AS goal_description
        FROM user_ u
        LEFT JOIN user_health_goal uhg ON u.user_id = uhg.user_id
        LEFT JOIN health_goal g ON uhg.goal_id = g.goal_id
        WHERE u.user_id = :user_id
    """)

    result = await db.execute(query, {"user_id": user_id})
    row = result.fetchone()

    if row:
        return {
            "user_id":          row.user_id,
            "first_name":       row.first_name,
            "email":            row.email,
            "allergies":        row.allergies,
            "diet_type":        row.diet_type,
            "weight":           row.current_weight_kg,
            "height":           row.height_cm,
            "goal_label":       row.goal_label,
            "goal_description": row.goal_description,
        }
    return None


# ==========================================
# 3. REQUÊTES DE SYNCHRONISATION (PG <-> MONGO)
# ==========================================

async def save_meal_to_postgres(db: AsyncSession, user_id: str, calories: int, meal_totals: dict) -> str:
    """
    Enregistre un nouveau repas dans PostgreSQL après l'analyse IA.
    Retourne l'ID du repas.
    """
    meal_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    # 1. Insertion du repas
    query_meal = text("""
        INSERT INTO meal (meal_id, user_id, consumed_at, quantity_grams, calories_consumed)
        VALUES (:meal_id, :user_id, :consumed_at, :quantity_grams, :calories_consumed)
    """)
    
    await db.execute(query_meal, {
        "meal_id": meal_id,
        "user_id": user_id,
        "consumed_at": now,
        "quantity_grams": 400, # Valeur estimée ou calculée
        "calories_consumed": int(calories)
    })
    
    return meal_id


async def save_ai_recommendation_link(db: AsyncSession, mongo_doc_id: str, rec_type: str = "MEAL_ANALYSIS") -> str:
    """
    Enregistre dans PostgreSQL la trace de la recommandation IA stockée dans MongoDB.
    C'est la table 'ai_recommendation' vue dans le schéma de l'ETL.
    """
    rec_id = str(uuid.uuid4())
    
    query = text("""
        INSERT INTO ai_recommendation (recommendation_id, mongodb_document_id, mongodb_collection, recommendation_type, confidence_score, status)
        VALUES (:rec_id, :mongo_id, :collection, :type, :score, :status)
    """)
    
    await db.execute(query, {
        "rec_id": rec_id,
        "mongo_id": mongo_doc_id,
        "collection": "meal_analysis",
        "type": rec_type,
        "score": 0.95, 
        "status": "COMPLETED"
    })
    
    return rec_id
