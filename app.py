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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
conversation_memory = {}

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

wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=True
)

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
    SELECT p.ID, p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 15
    """
    items = db_query(query)
    if items:
        return "\n".join([f"- {i['post_title']} (ID: {i['ID']}): {i['prix']}€" for i in items])
    return "Catalogue vide."

def create_woo_order(product_id, customer_email, quantity=1):
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
            return f"COMMANDE RÉUSSIE : Numéro officiel #{response.json()['id']}"
        return "Erreur lors de la création sur le site."
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def ask_ai(user_id, question):
    history = conversation_memory.get(user_id, [])
    
    # On récupère TOUJOURS le catalogue pour que l'IA connaisse les IDs
    catalogue_actuel = get_catalog()

    prompt_system = (
        f"Tu es l'assistant de vente Graham Shopping.\n{shop_info}\n\n"
        f"VOICI TES PRODUITS EN STOCK (ID et Noms) :\n{catalogue_actuel}\n\n"
        "CONSIGNES DE VENTE :\n"
        "1. Ne demande JAMAIS l'ID d'un produit au client. Utilise les IDs listés ci-dessus.\n"
        "2. Si le client veut un produit, demande-lui uniquement son EMAIL pour valider.\n"
        "3. Une fois l'email reçu, utilise l'outil 'create_woo_order' immédiatement.\n"
        "4. N'invente jamais de numéro de commande. Donne le numéro officiel retourné par l'outil.\n"
        "5. Sois chaleureux, pas technique."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande réelle dans la boutique",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "L'ID numérique du produit trouvé dans le catalogue"},
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
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            messages.append(response_message)
            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                # Exécution réelle
                res_commande = create_woo_order(args.get("product_id"), args.get("customer_email"), args.get("quantity", 1))
                
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res_commande})
            
            # Réponse finale de confirmation
            final_response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
            reply = final_response.choices[0].message.content
        else:
            reply = response_message.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-10:]
        return reply

    except Exception as e:
        print(f"Erreur : {e}")
        return "Je suis à votre disposition pour prendre votre commande."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data: return jsonify({"reponse": "Erreur"}), 400
    question = data.get("question") or data.get("message") or ""
    user_id = data.get("user_id", "default")
    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
