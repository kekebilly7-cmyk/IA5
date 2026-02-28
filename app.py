from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
import openai
import re
import os
import time
from dotenv import load_dotenv

# 🔹 Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 OpenAI (Clé récupérée depuis Render ou .env)
openai.api_key = os.getenv("OPENAI_API_KEY")

# ===== INFOS BOUTIQUE =====
shop_info = """
Nom boutique : Graham Shopping
Adresse : 45 Rue de vaucelles 14000 Caen 
Email : info@grahamshoping.fr 
Téléphone : 0775958076 
Horaires : H24, 7/7 
"""

# 🔑 WooCommerce (URL et clés récupérées depuis Render ou .env)
wcapi = API(
    url=os.getenv("WC_URL", "https://grahamshoping.fr"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=False,  # Ajouté pour éviter les erreurs de certificat
    query_string_auth=True
)

# ===== STATUT COMMANDE =====
def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200 and "status" in order:
            status_map = {
                'pending': 'en attente de paiement',
                'processing': 'en cours de préparation',
                'on-hold': 'en pause',
                'completed': 'terminée',
                'cancelled': 'annulée',
                'refunded': 'remboursée',
                'failed': 'échouée'
            }
            statut_fr = status_map.get(order['status'], order['status'])
            return f"La commande #{order_id} est actuellement : {statut_fr}."
        else:
            return f"Désolé, je ne trouve pas la commande #{order_id}."
    except Exception as e:
        return f"Erreur de connexion à la boutique : {str(e)}"

# ===== IA AVEC MODÈLE À JOUR =====
def ask_ai(question):
    messages = [
        {
            "role": "system",
            "content": f"""
Tu es l'assistant officiel de Graham Shopping.
Voici les informations de la boutique :
{shop_info}

Si un client demande l'adresse, l'email, le téléphone ou les horaires,
tu dois répondre avec ces informations.
Sois poli et professionnel.
"""
        },
        {"role": "user", "content": question}
    ]

    # Retry pour éviter les micro-coupures
    for attempt in range(3):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # 🔹 Modèle mis à jour (plus performant)
                messages=messages,
                timeout=30
            )
            return response.choices[0].message["content"]
        except Exception as e:
            print(f"Tentative {attempt+1} échouée : {e}")
            time.sleep(1)

    return "Désolé, problème de connexion avec l'IA. Réessaie dans quelques secondes."

# ===== ROUTE CHAT =====
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"reponse": "Erreur : Aucune donnée reçue"}), 400

    # On accepte 'question' ou 'message' pour plus de flexibilité
    question = data.get("question") or data.get("message") or ""

    # 🔹 Détection de demande de statut de commande
    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums:
            return jsonify({"reponse": get_order_status(nums[0])})

    # 🔹 Réponse via l'IA
    reponse = ask_ai(question)
    return jsonify({"reponse": reponse})

# ===== KEEP ALIVE =====
@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    # 0.0.0.0 est obligatoire pour Render
    app.run(host='0.0.0.0', port=5000)