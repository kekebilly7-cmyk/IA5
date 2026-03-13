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

# Configuration OpenAI (Note: gpt-5 n'existe pas encore, j'ai mis gpt-4o-mini pour la performance/prix)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Mémoire conversationnelle
conversation_memory = {}

# Configuration Base de Données Hostinger
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
    """Récupère les produits réels avec Prix, Image et Description courte"""
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
            desc = i['description'].strip() if i['description'] else "Produit disponible chez Graham Shopping."
            cat_list.append(f"PRODUIT: {i['post_title']} | ID: {i['ID']} | PRIX: {prix}€ | IMAGE: {img} | DESC: {desc}")
        return "\n".join(cat_list)
    return "Le catalogue est actuellement vide."

def get_order_status(order_id):
    """Vérification du statut de commande via WooCommerce"""
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200:
            status_map = {'pending': 'en attente', 'processing': 'en cours de traitement', 'completed': 'Commande terminée', 'cancelled': 'Commande annulée'}
            return f"La commande #{order_id} est {status_map.get(order['status'], order['status'])}."
        return "je retrouve pas votre commande veuillez vérifier votre saisir du numéro commande."
    except:
        return "Erreur technique lors du suivi."

# --- FONCTION DE PAIEMENT (CHECKOUT) ---

def create_woo_order(product_id, customer_email, quantity=1):
    """Crée une commande et génère le lien de paiement réel"""
    data = {
        "status": "pending",
        "billing": {"email": customer_email},
        "line_items": [{"product_id": int(product_id), "quantity": int(quantity)}]
    }
    try:
        response = wcapi.post("orders", data)
        res_data = response.json()
        if response.status_code == 201:
            # On renvoie le lien de paiement direct de WooCommerce
            return f"La commande est prête ! Voici votre lien de paiement sécurisé : {res_data.get('payment_url')}"
        return f"Désolé, impossible de créer la commande : {res_data.get('message')}"
    except Exception as e:
        return f"Erreur de connexion WooCommerce : {str(e)}"

# --- LOGIQUE IA AVEC TOOLS ---

def ask_ai(user_id, question):
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []
    history = conversation_memory[user_id]

    catalogue = get_catalog()

    prompt_system = (
        f"Tu es l'assistant de vente de Graham Shop.\n{shop_info}\n\n"
        f"CATALOGUE EN DIRECT :\n{catalogue}\n\n"
        "RÈGLES CRITIQUES :\n"
        "1. Pour chaque produit, affiche l'image ainsi : ![Image](URL).\n"
        "2. Pour payer, tu DOIS demander l'EMAIL du client,après validation de son email demande nom et prénom,adresse de livraison et numéro de téléphone puis utiliser l'outil ne parle pas de outils dans la conversation avec le client'create_woo_order'.\n"
        "3. Ne propose JAMAIS de virement bancaire.\n"
        "4. Réponds toujours en français poli et parle beaucoup pour bien détaillé la procedure de comment tu vas créerla commande du client sans parler de l'outils create woo order."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande avec les adresses de livraison,email ,nom et prénom et numéro de téléphone du client et génère un lien de paiement Checkout",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "L'ID du produit"},
                    "customer_email": {"type": "string", "description": "L'email du client"},
                    "quantity": {"type": "integer", "default": 1}
                },
                "required": ["product_id", "customer_email"]
            }
        }
    }]

    messages = [{"role": "system", "content": prompt_system}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini", # Remplace par ton modèle si nécessaire
            messages=messages,
            tools=tools
        )
        msg = response.choices[0].message

        # Gestion de l'appel de fonction (Checkout)
        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                res = create_woo_order(args.get("product_id"), args.get("customer_email"))
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res})
            
            # Deuxième appel pour formater la réponse finale avec le lien
            final_res = client.chat.completions.create(model="gpt-5.4", messages=messages)
            reply = final_res.choices[0].message.content
        else:
            reply = msg.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-10:]
        return reply

    except Exception as e:
        print(f"Erreur : {e}")
        return "Je rencontre une petite difficulté, pouvez-vous reformuler ?"

# --- ROUTES ---

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    question = data.get("question") or data.get("message") or ""

    # Suivi de commande rapide
    if "commande" in question.lower() and re.search(r'\d+', question):
        order_id = re.findall(r'\d+', question)[0]
        return jsonify({"reponse": get_order_status(order_id)})

    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)







