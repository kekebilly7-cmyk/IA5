from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import re
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Vérif clé OpenAI
if not os.getenv("OPENAI_API_KEY"):
    print("ERREUR : OPENAI_API_KEY manquante")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

shop_info = """
Nom boutique : Graham Shopping
Adresse : 45 Rue de vaucelles 14000 Caen
Email : info@grahamshoping.fr
Téléphone : 0775958076
Horaires : H24, 7/7
"""

wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=True
)

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
            return f"La commande #{order_id} est : {status_map.get(order['status'], order['status'])}"
        return "Commande introuvable"
    except Exception as e:
        print("Erreur WooCommerce:", e)
        return "Erreur connexion boutique"

def ask_ai(question):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": f"Tu es l'assistant officiel. Infos boutique : {shop_info}"},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print("Erreur OpenAI:", e)
        return "Problème connexion IA"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"reponse": "Aucune donnée"}), 400

    question = data.get("question") or data.get("message") or ""

    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums:
            return jsonify({"reponse": get_order_status(nums[0])})

    return jsonify({"reponse": ask_ai(question)})

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)