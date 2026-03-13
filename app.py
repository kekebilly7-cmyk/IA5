from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import mysql.connector
import re
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration OpenAI - Utilisation de gpt-4o-mini (stable et performant)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = "gpt-4o-mini"

# Mémoire conversationnelle
conversation_memory = {}

# Configuration Base de Données
db_config = {
    "host": "sql1270.main-hosting.eu",
    "user": "u637875669_xOcRm",
    "password": "billykeke1234K@#",
    "database": "u637875669_mAofs",
    "raise_on_warnings": True
}

shop_info = """
Nom boutique : Graham Shop
Adresse : 45 Rue de Vaucelles 14000 Caen
Email : info@grahamshoping.fr
Téléphone : 0775958076
Horaires : H24, 7/7
"""

# Connexion API WooCommerce
wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=True
)

# --- FONCTIONS DE BASE DE DONNÉES ---

def db_query(query, params=(), fetchone=False):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Erreur DB: {e}")
        return None

def get_catalog():
    query = """
    SELECT p.ID, p.post_title, p.post_excerpt as description, 
           m1.meta_value as prix,
           (SELECT guid FROM wp_posts WHERE ID = m2.meta_value) as image_url
    FROM wp_posts p
    LEFT JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_thumbnail_id'
    WHERE p.post_type = 'product' 
    AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 20
    """
    items = db_query(query)
    if items:
        cat_list = []
        for i in items:
            prix = i['prix'] if i['prix'] else "0.00"
            img = i['image_url'] if i['image_url'] else "https://grahamshoping.fr/wp-content/uploads/woocommerce-placeholder.png"
            desc = i['description'].strip() if i['description'] else "Produit disponible."
            cat_list.append(f"PRODUIT: {i['post_title']} | ID: {i['ID']} | PRIX: {prix}€ | IMAGE: {img} | DESC: {desc}")
        return "\n".join(cat_list)
    return "Le catalogue est vide."

def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200:
            status_map = {'pending': 'en attente', 'processing': 'en cours', 'completed': 'terminée', 'cancelled': 'annulée'}
            return f"La commande #{order_id} est {status_map.get(order['status'], order['status'])}."
        return "Commande introuvable. Vérifiez le numéro."
    except:
        return "Erreur lors du suivi."

# --- FONCTION DE PAIEMENT (CHECKOUT MULTI-ARTICLES) ---

def create_woo_order(customer_email, items):
    """Crée une commande avec un panier d'articles et renvoie le lien de paiement"""
    data = {
        "status": "pending",
        "billing": {"email": customer_email},
        "line_items": items  # items est une liste [{'product_id': 123, 'quantity': 2}, ...]
    }
    try:
        response = wcapi.post("orders", data)
        res_data = response.json()
        if response.status_code == 201:
            return f"Succès : Voici le lien de paiement : {res_data.get('payment_url')}"
        return f"Erreur WooCommerce : {res_data.get('message')}"
    except Exception as e:
        return f"Erreur technique : {str(e)}"

# --- LOGIQUE IA ---

def ask_ai(user_id, question):
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []
    history = conversation_memory[user_id]

    catalogue = get_catalog()

    prompt_system = (
        f"Tu es l'assistant de Graham Shop.\n{shop_info}\n\n"
        f"CATALOGUE :\n{catalogue}\n\n"
        "RÈGLES :\n"
        "1. Affiche les images ainsi : ![Image](URL).\n"
        "2. Pour créer une commande : Demande l'EMAIL, NOM, PRÉNOM, ADRESSE et TÉLÉPHONE.\n"
        "3. Utilise 'create_woo_order' pour générer le lien de paiement. Additionne bien les quantités si le client veut plusieurs articles.\n"
        "4. Réponds toujours en français poli et détaillé."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande et génère un lien de paiement pour un panier d'articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string", "description": "Email du client"},
                    "items": {
                        "type": "array",
                        "description": "Liste des produits et quantités",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "integer"}
                            },
                            "required": ["product_id", "quantity"]
                        }
                    }
                },
                "required": ["customer_email", "items"]
            }
        }
    }]

    messages = [{"role": "system", "content": prompt_system}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                # Appel de la fonction avec les nouveaux paramètres
                res_content = create_woo_order(
                    customer_email=args.get("customer_email"),
                    items=args.get("items")
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_content
                })
            
            # Appel de confirmation final
            final_res = client.chat.completions.create(model=MODEL_NAME, messages=messages)
            reply = final_res.choices[0].message.content
        else:
            reply = msg.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-10:]
        return reply

    except Exception as e:
        print(f"Erreur IA : {e}")
        return "Le service est momentanément indisponible, veuillez réessayer dans un instant."

# --- ROUTES ---

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    question = data.get("question") or data.get("message") or ""

    if "commande" in question.lower() and re.search(r'\d+', question):
        order_id = re.findall(r'\d+', question)[0]
        return jsonify({"reponse": get_order_status(order_id)})

    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
