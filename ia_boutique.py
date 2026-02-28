from woocommerce import API
from openai import OpenAI  # 🔹 Changement ici
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# 🔹 Nouvelle façon d'initialiser le client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuration WooCommerce
wcapi = API(
    url=os.getenv("WC_URL", "https://grahamshoping.fr"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=False,
    query_string_auth=True
)

def repondre_client(question):
    """Appelle OpenAI pour répondre à la question du client"""
    try:
        # 🔹 Nouvelle syntaxe pour l'appel à l'IA
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "Tu es un assistant qui répond aux questions sur les commandes d'une boutique WooCommerce."
                },
                {"role": "user", "content": question}
            ]
        )
        # 🔹 Accès aux données légèrement différent (objet au lieu de dictionnaire)
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur OpenAI : {str(e)}"

def tester_derniere_commandes():
    """Récupère les dernières commandes et demande leur statut à l'IA"""
    try:
        response = wcapi.get("orders", params={"per_page": 5})
        derniere_commandes = response.json()
        
        if isinstance(derniere_commandes, dict) and "code" in derniere_commandes:
            print(f"Erreur WooCommerce API : {derniere_commandes['message']}")
            return

        for commande in derniere_commandes:
            if isinstance(commande, dict) and 'id' in commande:
                question = f"Quel est le statut de la commande #{commande['id']} ?"
                reponse = repondre_client(question)
                print(f"Commande #{commande['id']}: {reponse}")
            else:
                print("Données de commande reçues incorrectes.")
    except Exception as e:
        print(f"Erreur système : {str(e)}")

if __name__ == "__main__":
    tester_derniere_commandes()