from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI  # 🔹 CHANGEMENT ICI
import re
import os
import time
from dotenv import load_dotenv

# 🔹 Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 Initialisation MODERNE du client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== INFOS BOUTIQUE =====
shop_info = """
Nom boutique : Graham Shopping
Adresse : 45 Rue de vaucelles 14000 Caen 
Email : info@grahamshoping.fr 
Téléphone : 0775958076 
Horaires : H24, 7/7 
"""

# 🔑 WooCommerce
wcapi = API(
    url=os.getenv("WC_URL", "https://grahamshoping.fr"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=False,
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

# ===== IA AVEC SYNTAXE MODERNE =====
def ask_ai(question):
    messages = [
        {
            "role": "system",
            "content": f"Tu es l'assistant officiel de Graham Shopping. Infos boutique :\n{shop_info}"
        },
        {"role": "user", "content": question}
    ]

    for attempt in range(3):
        try:
            # 🔹 NOUVELLE SYNTAXE ICI
            response = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=messages,
                timeout=30
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Tentative {attempt+1} échouée : {e}")
            time.sleep(1)

    return "Désolé, problème de connexion avec l'IA. Réessaie dans quelques secondes."

# ===== ROUTES =====
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"reponse": "Erreur : Aucune donnée reçue"}), 400

    question = data.get("question") or data.get("message") or ""

    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums:
            return jsonify({"reponse": get_order_status(nums[0])})

    reponse = ask_ai(question)
    return jsonify({"reponse": reponse})

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)