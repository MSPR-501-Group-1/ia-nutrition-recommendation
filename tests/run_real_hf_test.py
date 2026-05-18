import asyncio
import os
import sys

# Ajout du dossier parent (racine du projet) au path pour que Python trouve le module 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.vision.huggingface_client import detect_food_with_hf

async def run_real_api_call():
    """
    Ce script effectue un VRAI appel à l'API Hugging Face pour vérifier la connexion
    et la validité de la clé API.
    """
    print("🤖 Démarrage du test d'intégration réel avec Hugging Face...")

    # --- PRÉREQUIS ---
    # 1. Le fichier .env doit exister à la racine du projet avec votre clé :
    #    HUGGINGFACE_API_KEY=hf_votreVraieCleApi
    #
    # 2. Une image de nourriture nommée 'frites.jpg' doit être dans le dossier 'tests/imgTest'.
    # -----------------

    # On construit les chemins vers les fichiers
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    env_path = os.path.join(project_root, ".env")
    image_path = os.path.join(os.path.dirname(__file__), "imgTest", "frites.jpg")

    if not os.path.exists(env_path):
        print(f"\n❌ ERREUR : Fichier .env introuvable à la racine du projet ({project_root}).")
        print("-> Le test ne peut pas continuer sans clé API.")
        return

    if not os.path.exists(image_path):
        print(f"\n❌ ERREUR : Image '{image_path}' introuvable.")
        print("-> Le test ne peut pas continuer sans image.")
        return

    print(f"📸 Lecture de l'image '{image_path}'...")
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    print("\n🚀 Tentative d'appel à l'API Hugging Face...")
    print("   (Ceci peut prendre jusqu'à 30 secondes si le modèle est en cours de chargement)")

    resultats = await detect_food_with_hf(image_bytes)

    print("\n" + "="*50)
    print("✅ RÉSULTAT REÇU :")
    print(resultats)
    print("="*50 + "\n")

    if isinstance(resultats, list) and len(resultats) > 0 and resultats[0].get("label") == "chicken":
        print("⚠️ ATTENTION : Vous avez reçu la réponse de SECOURS (mock). L'appel à l'API a échoué.")
    else:
        print("🎉 SUCCÈS ! La communication avec Hugging Face fonctionne.")

if __name__ == "__main__":
    asyncio.run(run_real_api_call())