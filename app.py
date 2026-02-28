<<<<<<< HEAD
from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
import openai
import re
import os
import time
from dotenv import load_dotenv

# 🔹 Charger .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    url="https://grahamshoping.fr",
    consumer_key="ck_607ce80b9a37a12ab09aa96e1ef5db52a65d57b4",
    consumer_secret="cs_f3578af8508cc5b327ecba62542a692635feda80",
    version="wc/v3"
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

# ===== IA AVEC RETRY =====
def ask_ai(question):
    messages = [
        {
            "role": "system",
            "content": f"""
Tu es l'assistant officiel de Graham Shopping.

Voici les informations de la boutique :
{shop_info}

Si un client demande adresse, email, téléphone ou horaires,
tu dois répondre avec ces informations.
Sois poli et professionnel.
"""
        },
        {"role": "user", "content": question}
    ]

    # Retry pour éviter Error 102 / ConnectionReset
    for attempt in range(3):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                timeout=30
            )
            return response.choices[0].message["content"]
        except Exception as e:
            print("Tentative échouée :", e)
            time.sleep(1)

    return "Désolé, problème de connexion avec l’IA. Réessaie dans quelques secondes."

# ===== ROUTE CHAT =====
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"reponse": "Erreur : Aucune donnée reçue"}), 400

    question = data.get("question", "")

    # 🔹 Statut commande
    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums:
            return jsonify({"reponse": get_order_status(nums[0])})

    # 🔹 IA
    reponse = ask_ai(question)
    return jsonify({"reponse": reponse})

# ===== KEEP ALIVE =====
@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
=======
from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
import openai
import re
import os
import time
from dotenv import load_dotenv

# 🔹 Charger .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# 🔑 OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    url="https://grahamshoping.fr",
    consumer_key="ck_607ce80b9a37a12ab09aa96e1ef5db52a65d57b4",
    consumer_secret="cs_f3578af8508cc5b327ecba62542a692635feda80",
    version="wc/v3"
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

# ===== IA AVEC RETRY =====
def ask_ai(question):
    messages = [
        {
            "role": "system",
            "content": f"""
Tu es l'assistant officiel de Graham Shopping.

Voici les informations de la boutique :
{shop_info}

Si un client demande adresse, email, téléphone ou horaires,
tu dois répondre avec ces informations.
Sois poli et professionnel.
"""
        },
        {"role": "user", "content": question}
    ]

    # Retry pour éviter Error 102 / ConnectionReset
    for attempt in range(3):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                timeout=30
            )
            return response.choices[0].message["content"]
        except Exception as e:
            print("Tentative échouée :", e)
            time.sleep(1)

    return "Désolé, problème de connexion avec l’IA. Réessaie dans quelques secondes."

# ===== ROUTE CHAT =====
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"reponse": "Erreur : Aucune donnée reçue"}), 400

    question = data.get("question", "")

    # 🔹 Statut commande
    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums:
            return jsonify({"reponse": get_order_status(nums[0])})

    # 🔹 IA
    reponse = ask_ai(question)
    return jsonify({"reponse": reponse})

# ===== KEEP ALIVE =====
@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
>>>>>>> d5ca23350dc7ab62640d618b94b08e9dd97bd7cd
    app.run(host='0.0.0.0', port=5000)