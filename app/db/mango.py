from app.db.database import AsyncSession
from sqlalchemy import text
from datetime import datetime, timezone


async def get_food_by_name(db: AsyncSession, name: str) -> dict | None:
    """
    Récupère les données nutritionnelles d'un aliment à partir de son nom.
    """
    query = text("""
        SELECT name, calories_g, protein_g, carbs_g, fat_g
        FROM ingredient
        WHERE name ILIKE :name
        LIMIT 1
    """)
    
    result = await db.execute(query, {"name": f"%{name}%"})
    row = result.fetchone()
    
    if row:
        return {
            "name": row.name,
            "calories": row.calories_g,
            "proteins": row.protein_g,
            "carbs": row.carbs_g,
            "fats": row.fat_g
        }
    return None

async def save_analysis_to_mongodb(mongo_db, user_id, photo_url, vision_results, nutrition_totals):
    document = {
        "user_id": user_id,
        "meal_type": "lunch", # ou calculé
        "photo_url": photo_url,
        "analyzed_at": datetime.now(timezone.utc),
        "vision_result": vision_results,
        "nutrition_result": nutrition_totals
    }
    result = await mongo_db.meal_analysis.insert_one(document)
    return str(result.inserted_id)