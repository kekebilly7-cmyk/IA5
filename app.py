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

# --- CONFIGURATION ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = "gpt-4o" 

conversation_memory = {}

# Utilisation des identifiants confirmés par votre SQL
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
Horaires : Ouvert 24h/24, 7j/7
"""

wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=True
)

# --- FONCTIONS BASE DE DONNÉES ---

def db_query(query, params=(), fetchone=False):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        result = cursor.fetchone() if fetchone else cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Erreur DB Query: {e}")
        return None

def save_sale_to_db(user_id, email, product_name, product_price, order_id, payment_link, status):
    """ 
    Enregistre la transaction en respectant STRICTEMENT la structure :
    (user_id, email, product_name, product_price, order_id, payment_link, status)
    """
    query = """
    INSERT INTO ai_sales (user_id, email, product_name, product_price, order_id, payment_link, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (user_id, email, product_name, product_price, order_id, payment_link, status)
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit() # Indispensable pour que les données apparaissent dans phpMyAdmin
        conn.close()
        print(f"--- LOG : Commande {order_id} insérée en base de données. ---")
    except Exception as e:
        print(f"--- ERREUR SQL : {e} ---")

# --- CATALOGUE ---

def get_catalog():
    query = """
    SELECT p.ID, p.post_title, m1.meta_value as prix,
           (SELECT guid FROM wp_posts WHERE ID = m2.meta_value) as image_url
    FROM wp_posts p
    LEFT JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_thumbnail_id'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    """
    items = db_query(query)
    if items:
        cat_list = [f"PRODUIT: {i['post_title']} | ID: {i['ID']} | PRIX: {i['prix']}€" for i in items]
        return "\n".join(cat_list)
    return "Catalogue vide."

# --- LOGIQUE COMMANDE ---

def create_woo_order(user_id, customer_email, first_name, last_name, phone, address, city, postcode, country, items):
    data = {
        "status": "pending",
        "billing": {
            "first_name": first_name, "last_name": last_name, "address_1": address,
            "city": city, "postcode": postcode, "country": country,
            "email": customer_email, "phone": phone
        },
        "line_items": items
    }

    try:
        response = wcapi.post("orders", data)
        res_data = response.json()

        if response.status_code == 201:
            payment_url = res_data.get("payment_url")
            order_id = str(res_data.get("id"))
            total_price = res_data.get("total")
            
            # On récupère le nom du produit via le catalogue pour le log SQL
            p_name = f"Commande #{order_id}"
            if items:
                p_name = f"Produit ID: {items[0].get('product_id')}"

            # APPEL DE LA SAUVEGARDE SQL (Basé sur votre commande CREATE TABLE)
            save_sale_to_db(
                user_id=user_id,
                email=customer_email,
                product_name=p_name,
                product_price=total_price,
                order_id=order_id,
                payment_link=payment_url,
                status="pending"
            )

            return f"Parfait ! Votre commande est prête. Vous pouvez finaliser le paiement ici : {payment_url}"
        
        return "Désolé, une erreur est survenue lors de la création de la commande."
    except Exception as e:
        return f"Erreur technique : {str(e)}"

# --- IA ---

def ask_ai(user_id, question):
    if user_id not in conversation_memory:
        conversation_memory[user_id] = []

    history = conversation_memory[user_id]
    catalogue = get_catalog()

    prompt_system = (
        f"Tu es le conseiller Graham Shop. {shop_info}\n CATALOGUE :\n{catalogue}\n"
        "Demande les infos de livraison (email, nom, adresse, ville, tel) pour créer une commande."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande WooCommerce.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string"},
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "phone": {"type": "string"},
                    "address": {"type": "string"},
                    "city": {"type": "string"},
                    "postcode": {"type": "string"},
                    "country": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "integer"}
                            }
                        }
                    }
                },
                "required": ["customer_email", "first_name", "last_name", "phone", "address", "city", "postcode", "country", "items"]
            }
        }
    }]

    messages = [{"role": "system", "content": prompt_system}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        response = client.chat.completions.create(model=MODEL_NAME, messages=messages, tools=tools)
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                res_content = create_woo_order(user_id=user_id, **args)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res_content})

            final = client.chat.completions.create(model=MODEL_NAME, messages=messages)
            reply = final.choices[0].message.content
        else:
            reply = msg.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-5:]
        return reply
    except Exception as e:
        print(f"Erreur : {e}")
        return "Une petite erreur technique, réessayez dans un instant."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = str(data.get("user_id", "default"))
    question = data.get("question") or data.get("message") or ""
    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
