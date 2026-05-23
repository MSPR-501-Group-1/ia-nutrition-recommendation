# ia-nutrition-recommendation

# pour la gestion des test automatisé 

bash 
pytest tests/
python -m pytest tests/ -v  Si la commande precedente ne marche pas (commande introuvable)


python -m uvicorn main:app --reload

swagger
http://localhost:8000/docs#/

http://127.0.0.1:8000/redoc

http://127.0.0.1:8000/docs#/Nutrition/search_ingredient_api_v1_ingredients_search_get

telecharger le modele 
ollama pull llama3.1

tester depuis le terminal
ollama run llama3.1 "Donne un conseil nutrition rapide"

# Terminal 1 — IA FastAPI
Set-Location "c:\Users\sisin\cours_Bachelor_Epsi\mspr\2eme mspr\Main\ia-nutrition-recommendation"
& "C:\Users\sisin\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn main:app --reload --port 8000

# Terminal 2 — Backend Node.js (si besoin)
Set-Location "c:\Users\sisin\cours_Bachelor_Epsi\mspr\2eme mspr\Main\backend-main"
npm start


MealPlanResponse
├── status / request_id / generated_at          ← REQUIRED
├── ai_model / confidence_score                 ← optional
├── user_context { goal, allergies, diet_type } ← optional
├── plan_metadata                               ← REQUIRED
│   ├── duration_days, target_calories_daily    ← REQUIRED
│   ├── target_macros { protein, carbs, fat }   ← REQUIRED
│   └── budget_constraint_eur                   ← optional
├── daily_plans[]                               ← REQUIRED
│   ├── day_number, total_calories, total_macros← REQUIRED
│   └── meals[]
│       ├── meal_type (breakfast/lunch/dinner/snack) ← REQUIRED
│       └── recipe
│           ├── recipe_id, title, instructions  ← REQUIRED (de ta DB)
│           ├── prep_time_min, cook_time_min, image_url, tags ← optional (Ollama)
│           ├── ingredients[]
│           │   ├── ingredient_id, name, category, quantity_g ← REQUIRED
│           │   ├── macros_per_serving { calories, protein, carbs, fat, fiber } ← REQUIRED
│           │   └── estimated_cost_eur          ← optional (à implémenter)
│           ├── nutritional_summary             ← REQUIRED (calculé)
│           ├── estimated_cost_eur              ← REQUIRED
│           └── ai_notes[]                      ← optional (Ollama)
├── shopping_list { grouped_by_category }       ← optional
└── nutritional_insights
    ├── detected_deficits / detected_excesses   ← optional
    └── ai_global_recommendation                ← optional (Ollama)



to do list

1 
Tester les endpoints via Swagger (python main.py → http://localhost:8001/docs) — vérifier que les 7 routes répondent correctement

2
Corriger les TODOs dans app/services/nutrition/meal_plan_adapter.py : target_calories_daily hardcodé à 2000, macros à 0

3
Vérifier les response_model sur les routes nutrition — certains retournent peut-être des dict au lieu de modèles Pydantic typés
