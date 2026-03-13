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

# Configuration OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = "gpt-5.4"

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
Horaires : Ouvert 24h/24, 7j/7
"""

# Connexion API WooCommerce
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

        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()

        conn.close()
        return result

    except Exception as e:
        print(f"Erreur DB: {e}")
        return None

# --- MODIFICATION: récupérer tous les produits avec image, prix et description ---
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
    ORDER BY p.post_date DESC
    """

    items = db_query(query)

    if items:
        cat_list = []

        for i in items:
            prix = i['prix'] if i['prix'] else "0.00"
            img = i['image_url'] if i['image_url'] else "https://grahamshoping.fr/wp-content/uploads/woocommerce-placeholder.png"
            desc = i['description'].strip() if i['description'] else "Produit disponible."

            cat_list.append(
                f"PRODUIT: {i['post_title']} | ID: {i['ID']} | PRIX: {prix}€ | IMAGE: ![Image]({img}) | DESC: {desc}"
            )

        return "\n".join(cat_list)

    return "Le catalogue est vide actuellement."


def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()

        if response.status_code == 200:

            status_map = {
                'pending': 'en attente de paiement ',
                'processing': 'en cours de traitement de paiement ',
                'completed': 'la commande est terminée',
                'cancelled': 'a été annulée  veuillez contacter le service clientèle',
            }

            return f"La commande #{order_id} est {status_map.get(order['status'], order['status'])}."

        return "je retrouve pas votre Commande veuillez verifier votre numéro de suivi ou contacter le service client."

    except:
        return "Erreur lors du suivi de la commande."


# --- CREATION COMMANDE (LIVRAISON MONDIALE) ---

def create_woo_order(customer_email, first_name, last_name, phone, address, city, postcode, country, items):

    data = {
        "status": "pending",
        "billing": {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": address,
            "city": city,
            "postcode": postcode,
            "country": country,
            "email": customer_email,
            "phone": phone
        },
        "shipping": {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": address,
            "city": city,
            "postcode": postcode,
            "country": country
        },
        "line_items": items
    }

    try:

        response = wcapi.post("orders", data)
        res_data = response.json()

        if response.status_code == 201:

            payment_url = res_data.get("payment_url")

            return f"Votre commande est créée avec succès. Voici votre lien de paiement vous pouvez à present payer avec votre carte bancaire ou autres moyens à votre actif : {payment_url}"

        return f"Erreur WooCommerce : {res_data}"

    except Exception as e:
        return f"Erreur technique : {str(e)}"


# --- LOGIQUE IA ---

def ask_ai(user_id, question):

    if user_id not in conversation_memory:
        conversation_memory[user_id] = []

    history = conversation_memory[user_id]

    catalogue = get_catalog()

    prompt_system = (
        f"Tu es un vendeur e-commerce professionnel de Graham Shop. "
        f"reponds aux premiers messages avec quelques articles et photos. "
        f"Réponds de manière chaleureuse et naturelle comme un conseiller humain. "
        f"Utilise des phrases complètes et inspire confiance au client.\n\n"
        f"{shop_info}\n\n"
        f"CATALOGUE :\n{catalogue}\n\n"
        "RÈGLES :\n"
        "1. Affiche les images avec : ![Image](URL)\n"
        "2. Pour créer une commande demande EMAIL, NOM, PRÉNOM, ADRESSE, VILLE, CODE POSTAL, PAYS et TÉLÉPHONE.\n"
        "3. Utilise la fonction create_woo_order pour générer le lien de paiement.\n"
        "4. Réponds toujours en français poli et parle beaucoup pour bien expliquer la procedure à suivre pour que tu crée la commande bien détaillée."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande WooCommerce et renvoie le lien de paiement.",
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
                            },
                            "required": ["product_id", "quantity"]
                        }
                    }
                },
                "required": [
                    "customer_email",
                    "first_name",
                    "last_name",
                    "phone",
                    "address",
                    "city",
                    "postcode",
                    "country",
                    "items"
                ]
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

                res_content = create_woo_order(
                    customer_email=args.get("customer_email"),
                    first_name=args.get("first_name"),
                    last_name=args.get("last_name"),
                    phone=args.get("phone"),
                    address=args.get("address"),
                    city=args.get("city"),
                    postcode=args.get("postcode"),
                    country=args.get("country"),
                    items=args.get("items")
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": res_content
                })

            final = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages
            )

            reply = final.choices[0].message.content

        else:

            reply = msg.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})

        conversation_memory[user_id] = history[-10:]

        return reply

    except Exception as e:

        print(f"Erreur IA : {e}")

        return "Le service est momentanément indisponible."


# --- ROUTE API ---

@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json()

    user_id = data.get("user_id", "default")
    question = data.get("question") or data.get("message") or ""

    if "commande" in question.lower() and re.search(r'\d+', question):

        order_id = re.findall(r'\d+', question)[0]

        return jsonify({
            "reponse": get_order_status(order_id)
        })

    return jsonify({
        "reponse": ask_ai(user_id, question)
    })


# --- LANCEMENT SERVEUR ---

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
