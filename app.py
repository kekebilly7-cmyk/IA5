from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import mysql.connector
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Mémoire conversationnelle
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
    """Récupère les produits depuis la table active (wp_posts)"""
    # CORRECTION : Utilisation du préfixe wp_ au lieu de vkccpq_wp_
    query = """
    SELECT p.ID, p.post_title, p.post_excerpt as description, 
           m1.meta_value as prix,
           (SELECT guid FROM wp_posts WHERE ID = m2.meta_value) as image_url
    FROM wp_posts p
    LEFT JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_thumbnail_id'
    WHERE p.post_type = 'product' 
    AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 30
    """
    items = db_query(query)
    
    if items:
        cat_list = []
        for i in items:
            # Gestion du prix
            prix_val = i['prix'] if (i['prix'] and str(i['prix']).strip() != "") else "0.00"
            # Gestion de l'image
            img = i['image_url'] if i['image_url'] else "https://grahamshoping.fr/wp-content/uploads/woocommerce-placeholder.png"
            # Nettoyage description
            desc = i['description'].strip() if (i['description'] and i['description'].strip() != "") else "Produit disponible chez Graham Shopping."
            
            cat_list.append(f"PRODUIT: {i['post_title']} | ID: {i['ID']} | PRIX: {prix_val}€ | IMAGE: {img} | DESC: {desc}")
        
        full_catalog = "\n".join(cat_list)
        print(f"\n--- CATALOGUE DÉTECTÉ ({len(items)} produits) ---\n{full_catalog[:500]}...\n")
        return full_catalog
    
    print("\n--- ERREUR : Catalogue vide dans la table wp_posts ---\n")
    return "Le catalogue est actuellement vide."

def create_woo_order(product_id, customer_email, quantity=1):
    data = {
        "status": "pending",
        "payment_method": "other",
        "payment_method_title": "Paiement sécurisé Graham Shopping",
        "billing": {"email": customer_email},
        "line_items": [{"product_id": int(product_id), "quantity": int(quantity)}]
    }
    try:
        response = wcapi.post("orders", data)
        res_data = response.json()
        if response.status_code == 201:
            return f"SUCCÈS : Commande créée. Lien de paiement : {res_data.get('payment_url')}"
        return f"Erreur : {res_data.get('message')}"
    except Exception as e:
        return f"Erreur technique : {str(e)}"

def ask_ai(user_id, question, history):
    catalogue = get_catalog()
    
    prompt_system = (
        f"Tu es l'assistant commercial expert de Graham Shopping.\n{shop_info}\n\n"
        f"CATALOGUE RÉEL DISPONIBLE :\n{catalogue}\n\n"
        "DIRECTIVES STRICTES :\n"
        "1. Affiche TOUJOURS la photo en Markdown pour chaque produit : ![Image](URL).\n"
        "2. Donne obligatoirement le PRIX et la DESCRIPTION (DESC).\n"
        "3. Ne dis jamais que tu ne peux pas voir les photos.\n"
        "4. Pour commander : demande l'EMAIL puis utilise 'create_woo_order'."
    )

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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools
        )
        msg = response.choices[0].message
        
        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                res = create_woo_order(args.get("product_id"), args.get("customer_email"), args.get("quantity", 1))
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res})
            
            final_response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
            reply = final_response.choices[0].message.content
        else:
            reply = msg.content
            
        return reply
    except Exception as e:
        print(f"Erreur OpenAI: {e}")
        return "Je suis là pour vous aider avec vos achats."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id", "default")
    question = data.get("question") or data.get("message") or ""
    
    if user_id not in conversation_memory:
        conversation_memory[user_id] = {'history': [], 'last_seen': time.time()}
    
    history = conversation_memory[user_id]['history']
    reply = ask_ai(user_id, question, history)

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply})
    conversation_memory[user_id]['history'] = history[-10:]
    conversation_memory[user_id]['last_seen'] = time.time()

    return jsonify({"reponse": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
