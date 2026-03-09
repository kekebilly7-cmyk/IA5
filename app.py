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
    """Récupère les produits avec leur VRAI ID WordPress"""
    query = """
    SELECT p.ID, p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 20
    """
    items = db_query(query)
    if items:
        # On formate clairement pour que l'IA ne confonde pas avec AliExpress
        return "\n".join([f"NOM: {i['post_title']} | ID_WORDPRESS: {i['ID']} | PRIX: {i['prix']}€" for i in items])
    return "Catalogue vide."

def create_woo_order(product_id, customer_email, quantity=1):
    """Crée la commande et log l'erreur si besoin"""
    print(f"--- Tentative de commande : ID {product_id} pour {customer_email} ---")
    
    data = {
        "payment_method": "cod",
        "payment_method_title": "Paiement à la livraison / Test",
        "set_paid": False,
        "billing": {
            "email": customer_email,
            "first_name": "Client",
            "last_name": "IA"
        },
        "line_items": [{"product_id": int(product_id), "quantity": int(quantity)}]
    }
    
    try:
        response = wcapi.post("orders", data)
        res_data = response.json()
        
        if response.status_code == 201:
            print(f"✅ SUCCÈS : Commande #{res_data['id']} créée.")
            return f"COMMANDE RÉUSSIE : Numéro officiel #{res_data['id']}"
        else:
            print(f"❌ ERREUR WOOCOMMERCE : {res_data}")
            return f"Erreur WooCommerce : {res_data.get('message', 'ID produit incorrect ou stock épuisé')}"
    except Exception as e:
        print(f"❌ ERREUR SYSTÈME : {str(e)}")
        return f"Erreur technique : {str(e)}"

def ask_ai(user_id, question):
    history = conversation_memory.get(user_id, [])
    
    # On injecte le catalogue frais
    catalogue = get_catalog()

    prompt_system = (
        f"Tu es l'assistant Graham Shopping.\n{shop_info}\n\n"
        f"VOICI TA LISTE DE PRODUITS OFFICIELLE (ID_WORDPRESS uniquement) :\n{catalogue}\n\n"
        "RÈGLES CRUCIALES :\n"
        "1. IGNORE TOTALEMENT les numéros longs (ex: 1005...) que le client pourrait envoyer. Ce sont des IDs AliExpress, ils ne marchent pas.\n"
        "2. Identifie le produit demandé par le client dans la LISTE OFFICIELLE ci-dessus.\n"
        "3. Utilise uniquement l'ID_WORDPRESS associé (ex: 742) pour l'outil 'create_woo_order'.\n"
        "4. Si le client veut acheter, demande juste son EMAIL.\n"
        "5. Ne demande JAMAIS d'ID au client. C'est toi l'expert, tu les as dans ta liste.\n"
        "6. Ne dis pas 'Je vais essayer', dis 'Je m'en occupe'."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "create_woo_order",
            "description": "Crée une commande réelle dans WooCommerce",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "L'ID_WORDPRESS du produit"},
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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        msg = response.choices[0].message
        
        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                # L'IA appelle la fonction avec le bon ID
                resultat = create_woo_order(args.get("product_id"), args.get("customer_email"), args.get("quantity", 1))
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": resultat})
            
            final_res = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
            reply = final_res.choices[0].message.content
        else:
            reply = msg.content

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[user_id] = history[-10:]
        return reply

    except Exception as e:
        print(f"Erreur Ask_AI: {e}")
        return "Désolé, je rencontre une difficulté. Pouvez-vous répéter votre demande ?"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data: return jsonify({"reponse": "Erreur"}), 400
    question = data.get("question") or data.get("message") or ""
    user_id = data.get("user_id", "default")
    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
