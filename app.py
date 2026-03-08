from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import mysql.connector
import re
import os
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------- CONFIGURATION OPENAI ----------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------- MÉMOIRE ISOLÉE PAR USER_ID ----------------
conversation_memory = {}  
user_data_memory = {}

# ---------------- CONFIGURATION BDD ----------------
db_config = {
    "host": os.getenv("DB_HOST") or "sql1270.main-hosting.eu",
    "user": os.getenv("DB_USER") or "u637875669_xOcRm",
    "password": os.getenv("DB_PASSWORD") or "billykeke1234K@#",
    "database": os.getenv("DB_NAME") or "u637875669_mAofs",
    "connect_timeout": 10
}

# ---------------- UTILITAIRES BDD ----------------
def db_query(query, params=(), fetchone=False):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        if query.strip().upper().startswith("SELECT"):
            result = cursor.fetchone() if fetchone else cursor.fetchall()
        else:
            conn.commit()
            result = cursor.lastrowid
        conn.close()
        return result
    except Exception as e:
        print(f"Erreur DB: {e}")
        return None

def save_conversation(user_id, email, message_user, message_ai):
    query = """
        INSERT INTO conversations (user_id, email, message_user, message_ai, created_at)
        VALUES (%s, %s, %s, %s, %s)
    """
    db_query(query, (user_id, email, message_user, message_ai, datetime.now()))

# ---------------- NETTOYAGE MÉMOIRE VIVE ----------------
def cleanup_memory():
    while True:
        now = datetime.now()
        keys_to_del = [k for k, v in conversation_memory.items() 
                       if now - v.get("last_active", now) > timedelta(minutes=30)]
        for k in keys_to_del:
            del conversation_memory[k]
            if k in user_data_memory: del user_data_memory[k]
        time.sleep(600)

threading.Thread(target=cleanup_memory, daemon=True).start()

# ---------------- CONFIGURATION BOUTIQUE ----------------
shop_info = """
Boutique : Graham Shopping | Caen, France
Contact boutique : info@grahamshoping.fr | 0775958076
"""

wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3"
)

# ---------------- FONCTIONS MÉTIER ----------------

def get_customer_by_email(email):
    try:
        response = wcapi.get("customers", params={"email": email})
        data = response.json()
        return data[0]["id"] if response.status_code == 200 and data else None
    except: return None

def db_get_catalog():
    query = """
    SELECT p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix
    FROM vkccpq_wp_posts p
    INNER JOIN vkccpq_wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 15
    """
    items = db_query(query)
    if items:
        return "\n".join([f"- {i['post_title']} : {i['prix']}€" for i in items])
    return "Catalogue actuellement indisponible."

def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200:
            return f"La commande #{order_id} est actuellement : {order['status']}."
        return "Commande introuvable."
    except: return "Erreur de vérification."

# ---------------- LOGIQUE IA AVEC RESET ET SÉPARATION ----------------

def ask_ai(user_id, question):
    uid = str(user_id).strip()
    
    if uid not in user_data_memory:
        user_data_memory[uid] = {"email": None, "customer_id": None}
    if uid not in conversation_memory:
        conversation_memory[uid] = {"history": [], "last_active": datetime.now()}

    # Détection Email
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', question)
    if email_match:
        email = email_match.group(0).lower()
        cid = get_customer_by_email(email)
        
        if cid:
            # SÉCURITÉ : RESET de l'historique pour éviter le mélange entre utilisateurs
            conversation_memory[uid]["history"] = [] 
            
            user_data_memory[uid]["email"] = email
            user_data_memory[uid]["customer_id"] = cid
            
            reply = f"Compte reconnu ✅. Votre session a été réinitialisée pour l'email {email}. Comment puis-je vous aider ?"
            save_conversation(uid, email, question, reply)
            return reply
        return "Email non reconnu. Veuillez créer un compte sur le site de notre boutique."

    current_email = user_data_memory[uid]["email"]
    history = conversation_memory[uid]["history"]
    catalog_data = db_get_catalog()
    
    # PROMPT AVEC SÉPARATION STRICTE IDENTITÉ / BOUTIQUE
    prompt_system = (
        f"Tu es l'assistant de Graham Shopping.\n\n"
        f"INFOS CONTACT BOUTIQUE : {shop_info}\n"
        f"IDENTITÉ DU CLIENT ACTUEL : {current_email if current_email else 'Non identifié'}\n\n"
        f"=== CATALOGUE Graham Shopping ===\n{catalog_data}\n================================\n\n"
        "CONSIGNES CRITIQUES :\n"
        "1. Si on te demande 'quel est MON mail', donne l'IDENTITÉ DU CLIENT ACTUEL et non celui de la boutique.\n"
        "2. Ne cite que les produits du CATALOGUE ci-dessus. Si absent, dis que nous ne l'avons pas.\n"
        "3. L'historique ne contient que les messages de ce client précis.\n"
        "4. Température : 0 (FACTUEL)."
    )

    messages = [{"role": "system", "content": prompt_system}] + history + [{"role": "user", "content": question}]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0 
        )
        reply = response.choices[0].message.content

        # Sauvegarde dans l'historique isolé
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        conversation_memory[uid]["history"] = history[-10:]
        conversation_memory[uid]["last_active"] = datetime.now()
        
        save_conversation(uid, current_email, question, reply)
        return reply
    except Exception as e:
        print(f"Erreur : {e}")
        return "Un problème technique survient."

# ---------------- ROUTE API ----------------

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = str(data.get("user_id", "session_unique"))
    question = data.get("question") or data.get("message") or ""

    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums: return jsonify({"reponse": get_order_status(nums[0])})

    return jsonify({"reponse": ask_ai(user_id, question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
