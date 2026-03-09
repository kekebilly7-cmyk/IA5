from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import mysql.connector
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration OpenAI
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
Nom boutique : Graham Shopping
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
    SELECT p.ID, p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix, m2.meta_value as stock
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_stock'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 10
    """
    items = db_query(query)
    if items:
        liste = "\n".join([f"- {i['post_title'].upper()} (ID: {i['ID']}): {i['prix']}€ (Stock: {i['stock'] or 'Dispo'})" for i in items])
        return f"\nVoici nos articles disponibles:\n{liste}"
    return "\nLe catalogue est actuellement vide."

def get_product_info(product_name):
    if not product_name or len(product_name) < 2:
        return ""
    query = """
    SELECT p.ID, p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix, m2.meta_value as stock
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_stock'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    AND p.post_title LIKE %s LIMIT 1
    """
    res = db_query(query, ("%" + product_name.strip() + "%",), fetchone=True)
    if res:
        stock = res['stock'] if res['stock'] not in [None, ''] else "Disponible"
        return f"Produit réel : {res['post_title'].upper()} | ID: {res['ID']} | Prix : {res['prix']}€ | Stock : {stock}"
    return ""

def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200 and "status" in order:
            status_map = {'pending': 'en attente', 'processing': 'en cours', 'completed': 'terminée', 'cancelled': 'annulée'}
            return f"Votre commande #{order_id} est {status_map.get(order['status'], order['status'])}."
        return "Commande introuvable."
    except:
        return "Erreur de vérification."

# --- NOUVELLE FONCTION : CRÉATION RÉELLE WOOCOMMERCE ---
def create_woo_order(product_id, customer_email, quantity=1):
    """Crée une vraie commande dans WooCommerce et retourne l'ID"""
    data = {
        "payment_method": "other",
        "payment_method_title": "Paiement en ligne",
        "set_paid": False,
        "billing": {"email": customer_email},
        "line_items": [{"product_id": product_id, "quantity": quantity}]
    }
    try:
        response = wcapi.post("orders", data)
        if response.status_code == 201:
            order_data = response.json()
            return f"SUCCÈS : Commande créée avec le numéro RÉEL #{order_data['id']}"
        return "ERREUR : Impossible de créer la commande sur WooCommerce."
    except Exception as e:
        return f"ERREUR TECHNIQUE : {str(e)}"

# --- LOGIQUE IA ---
def ask_ai(user_id, question):
    history = conversation_memory.get(user_id, [])
    low_q = question.lower()
    context_dynamique = ""

    if any(word in low_q for word in ["catalogue", "boutique", "vends", "articles"]):
        context_dynamique = get_catalog()
    elif any(word in low_q for word in ["prix", "stock", "combien"]):
        mots = [w for w in low_q.replace('?', '').split() if w not in ["le", "prix", "combien"]]
        context_dynamique = get_product_info(" ".join(mots)) or get_catalog()

    prompt_system = (
        f"Tu es l'assistant Graham Shopping.\n{shop_info}\n{context_dynamique}\n"
        "CONSIGNE STRICTE : Ne donne JAMAIS de numéro de commande imaginaire. "
        "Pour valider une commande, utilise TOUJOURS l'outil 'create_woo_order'. "
        "Si tu n'as pas l'email du client, demande-le avant de commander."
    )

    # Définition des outils pour OpenAI
    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande réelle dans WooCommerce",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "customer_email": {"type": "string"},
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
        # Premier appel pour voir si l'IA veut utiliser un outil
        response = client.chat.completions.create(
            model="gpt-5-mini", # gpt-4o recommandé pour les tools
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        
        # Vérification si l'IA appelle la fonction
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                if tool_call.function.name == "create_woo_order":
                    args = json.loads(tool_call.function.arguments)
                    res_commande = create_woo_order(args.get("product_id"), args.get("customer_email"), args.get("quantity", 1))
                    
                    # On renvoie le résultat de la vraie commande à l'IA
                    messages.append(response_message)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res_commande})
                    
                    # Deuxième appel pour que l'IA confirme au client avec le vrai numéro
                    second_response = client.chat.completions.create(model="gpt-5-mini", messages=messages)
                    reply = second_response.choices[0].message.content
        else:
            reply = response_message.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-10:]
        return reply

    except Exception as e:
        print(f"Erreur : {e}")
        return "Désolé, j'ai un problème pour valider la commande."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data: return jsonify({"reponse": "Erreur"}), 400
    question = data.get("question") or data.get("message") or ""
    user_id = data.get("user_id", "default")

    if "commande" in question.lower() and any(char.isdigit() for char in question):
        nums = re.findall(r'\d+', question)
        if nums: return jsonify({"reponse": get_order_status(nums[0])})

    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
