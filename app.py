# Mise à jour du 03 mars - Version Optimisée
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
    "database": "u637875669_mAofs",
    "raise_on_warnings": True
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
    """Récupère les derniers produits avec prix formatés"""
    query = """
    SELECT p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix, m2.meta_value as stock
    FROM wp_posts p
    INNER JOIN wp_postmeta m1 ON p.ID = m1.post_id AND m1.meta_key = '_price'
    LEFT JOIN wp_postmeta m2 ON p.ID = m2.post_id AND m2.meta_key = '_stock'
    WHERE p.post_type = 'product' AND p.post_status = 'publish'
    ORDER BY p.post_date DESC LIMIT 10
    """
    items = db_query(query)
    if items:
        liste = "\n".join([f"- {i['post_title']}: {i['prix']}€ (Stock: {i['stock'] or 'Dispo'})" for i in items])
        return f"\nVoici nos articles disponibles :\n{liste}"
    return "\nLe catalogue est actuellement vide."

def get_product_info(product_name):
    """Cherche un produit avec une recherche plus large"""
    if not product_name or len(product_name) < 2:
        return ""
        
    query = """
    SELECT p.post_title, CAST(m1.meta_value AS DECIMAL(10,2)) as prix, m2.meta_value as stock
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
    return ""

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

    # 1. Analyse pour le catalogue
    if any(word in low_q for word in ["catalogue", "boutique", "vends", "articles", "quoi", "disponible"]):
        context_dynamique = get_catalog()
    
    # 2. Analyse pour un produit spécifique (Recherche sur les mots importants)
    elif any(word in low_q for word in ["prix", "stock", "combien", "coûte"]):
        # Extraction du nom : on enlève les mots inutiles pour garder le nom du produit
        mots_a_enlever = ["le", "la", "du", "de", "prix", "stock", "combien", "coûte", "est", "quel", "quelle"]
        mots = [w for w in low_q.replace('?', '').split() if w not in mots_a_enlever]
        nom_produit = " ".join(mots)
        
        info_produit = get_product_info(nom_produit)
        if info_produit:
            context_dynamique = info_produit
        else:
            # Si pas trouvé, on donne le catalogue pour aider l'IA
            context_dynamique = get_catalog()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Tu es l'assistant de Graham Shopping. {shop_info} {context_dynamique}\nRéponds poliment. Si les prix sont dans le contexte, utilise-les."},
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
    
    if "commande" in question.lower():
        nums = re.findall(r'\d+', question)
        if nums: return jsonify({"reponse": get_order_status(nums[0])})

    return jsonify({"reponse": ask_ai(question)})

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
