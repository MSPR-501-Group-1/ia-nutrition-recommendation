# IA Nutrition Recommendation

Micro-service FastAPI — analyse de photos de repas et génération de plans nutritionnels via HuggingFace + Ollama.

---

## Lancer le service en local

**Prérequis :** Ollama lancé sur la machine + modèle téléchargé.

```powershell
# 1. Télécharger le modèle Ollama (une seule fois)
ollama pull qwen2.5:14b

# 2. Démarrer le service (depuis ce dossier)
python -m uvicorn main:app --reload --port 8002
```

Le service est disponible sur `http://localhost:8002`.

---

## Lancer via Docker (stack complète)

```bash
docker compose up ia-nutrition-recommendation
```

---

## Contrat d'API — tout est dans le Swagger

**Le contrat complet (routes, paramètres, corps de requête, réponses) est documenté automatiquement ici :**

```
http://localhost:8002/docs
```

Toutes les routes y sont, avec des exemples de requête et de réponse testables directement dans le navigateur.

Pour importer dans Postman :

```
http://localhost:8002/openapi.json
```

---

## Les 2 routes principales

| Méthode | Route | Ce que ça fait |
|---|---|---|
| `POST` | `/api/v1/users/{user_id}/analyze-meal` | Analyse une photo de repas — renvoie macros + recommandation Ollama |
| `POST` | `/api/v1/users/{user_id}/meal-plan?days=7` | Génère un plan de repas sur N jours via Ollama |

**`analyze-meal`** attend un `multipart/form-data` avec un champ `file` (image jpeg/png).
Paramètres query optionnels : `meal_type` (breakfast/lunch/dinner/snack), `portion_grams`, `with_recommendation`.

**`meal-plan`** n'a pas de body — juste le `user_id` dans l'URL et `days` en query param.
Le profil utilisateur (objectif, allergies, régime) est lu automatiquement depuis la base de données.

---

## Lancer les tests

```bash
pytest tests/
# ou si pytest n'est pas dans le PATH :
python -m pytest tests/ -v
```

---

## Variables d'environnement

Copier `.env.example` en `.env` et renseigner :

| Variable | Description |
|---|---|
| `HUGGINGFACE_API_KEY` | Clé API HuggingFace (vision Kimi-K2.5) |
| `OLLAMA_BASE_URL` | URL Ollama — `http://localhost:11434` en local, `http://host.docker.internal:11434` en Docker |
| `OLLAMA_MODEL` | Modèle Ollama utilisé (défaut : `qwen2.5:14b`) |
| `DB_HOST` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL |
| `MONGO_URI` / `MONGO_DB_NAME` | MongoDB |



1. Télécharge le fichier Ciqual
Sur ciqual.anses.fr → "Télécharger la table Ciqual" → version Excel FR 2020. Renomme le fichier en ciqual.xls et place-le dans scripts/.

2. Installe les dépendances (une seule fois)


pip install pandas openpyxl xlrd psycopg2-binary
3. Lance le script avec les variables de connexion à ta DB


DB_HOST=localhost DB_PORT=5432 DB_NAME=ton_db DB_USER=postgres DB_PASSWORD=tonmdp python scripts/seed_ciqual.py
Ce que fait le script :

Détecte automatiquement les colonnes Ciqual (gère .xls et .xlsx)
Mappe les groupes français → catégories DB (MEAT, VEGETABLE, DAIRY…)
Parse les valeurs spéciales Ciqual : "-" → NULL, "traces" → 0.001, "<0.05" → 0.025
Vérifie les noms existants avant d'insérer (pas de doublons)
N'insère que les lignes avec des calories valides
Résultat attendu : ~2800 aliments avec vrais noms français en plus des ~X entrées USDA existantes. Ensuite le meal-plan d'Ollama aura des vrais ingrédients ("Poulet rôti", "Brocoli cuit", "Riz basmati") au lieu des "CAMPBELL'S" et "BURGER KING".

Tu veux qu'on rebuilde le Docker après avoir ajouté le fix de la taille, et qu'on relance le meal-plan 3 jours pour voir la différence avant d'ajouter Ciqual ?