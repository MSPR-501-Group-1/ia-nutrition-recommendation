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
