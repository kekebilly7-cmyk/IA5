from flask import Flask, request, jsonify
from flask_cors import CORS
from woocommerce import API
from openai import OpenAI
import mysql.connector
import re
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuration Base de Données Hostinger
db_config = {
    "host": "sql1270.main-hosting.eu",
    "user": "u637875669_xOcRm",
    "password": "billykeke1234K@#",
    "database": "u637875669_mAofs"
}

shop_info = """
Nom boutique : Graham Shopping
Adresse : 45 Rue de vaucelles 14000 Caen
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
    """Récupère les 5 derniers produits en stock"""
    query = """
    SELECT p.post_title, m1.meta_value as prix, m2.meta_value as stock
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_stock'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 5
    """
    items = db_query(query)
    if items:
        liste = "\n".join([f"- {i['post_title']}: {i['prix']}€ (Stock: {i['stock'] or 'Dispo'})" for i in items])
        return f"\nVoici nos articles récents :\n{liste}"
    return "\nLe catalogue est actuellement vide."

def get_product_info(product_name):
    """Cherche prix et stock d'un produit spécifique"""
    query = """
    SELECT p.post_title, m1.meta_value as prix, m2.meta_value as stock
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_stock'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    AND p.post_title LIKE %s LIMIT 1
    """
    res = db_query(query, ("%" + product_name.strip() + "%",), fetchone=True)
    if res:
        stock = res['stock'] if res['stock'] not in [None, ''] else "Disponible"
        return f"\n[INFO RÉELLE] Produit: {res['post_title']} | Prix: {res['prix']}€ | Stock: {stock}"
    return "\n[INFO] Je n'ai pas trouvé ce produit spécifique, mais je peux lister le catalogue."

def get_order_status(order_id):
    try:
        response = wcapi.get(f"orders/{order_id}")
        order = response.json()
        if response.status_code == 200 and "status" in order:
            status_map = {'pending': 'en attente', 'processing': 'en cours', 'completed': 'terminée', 'cancelled': 'annulée'}
            return f"La commande #{order_id} est {status_map.get(order['status'], order['status'])}."
        return "Commande introuvable."
    except:
        return "Erreur lors de la vérification de la commande."

# --- LOGIQUE IA ---

def ask_ai(question):
    low_q = question.lower()
    context_dynamique = ""

    # Détection du besoin d'infos réelles
    if any(word in low_q for word in ["catalogue", "boutique", "vends", "articles", "quoi"]):
        context_dynamique = get_catalog()
    elif any(word in low_q for word in ["prix", "stock", "dispo", "combien"]):
        # On essaie d'extraire le dernier mot comme nom de produit
        produit_potentiel = question.split()[-1].replace('?', '')
        context_dynamique = get_product_info(produit_potentiel)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Tu es l'assistant de Graham Shopping. {shop_info} {context_dynamique}\nRéponds toujours poliment en utilisant ces données réelles."},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except:
        return "Désolé, j'ai un petit problème technique."

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data: return jsonify({"reponse": "Erreur"}), 400
    question = data.get("question") or data.get("message") or ""
    
    # Priorité : Statut de commande (détection de chiffres)
    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums: return jsonify({"reponse": get_order_status(nums[0])})

    return jsonify({"reponse": ask_ai(question)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)