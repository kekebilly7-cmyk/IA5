from woocommerce import API
import openai
import os
from dotenv import load_dotenv

# 🔹 Charger les variables d'environnement depuis .env
load_dotenv()

# 🔑 Clé OpenAI depuis .env
openai.api_key = os.getenv("OPENAI_API_KEY")

# 🔑 Clés WooCommerce depuis .env
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
    response = openai.ChatCompletion.create(
        model="gpt-5-mini",
        messages=[
            {
                "role": "system",
                "content": "Tu es un assistant qui répond aux questions sur les commandes et les descriptions d'articles d'une boutique WooCommerce."
            },
            {"role": "user", "content": question}
        ]
    )
    return response.choices[0].message['content']

def tester_derniere_commandes():
    """Récupère les 5 dernières commandes et demande leur statut à l'IA"""
    try:
        derniere_commandes = wcapi.get("orders", params={"per_page": 5}).json()
        print("DEBUG - Dernières commandes :", derniere_commandes)

        for commande in derniere_commandes:
            if isinstance(commande, dict) and 'id' in commande:
                question = f"Quel est le statut de la commande #{commande['id']} ?"
                reponse = repondre_client(question)
                print(f"Commande #{commande['id']}: {reponse}")
            else:
                print("Commande invalide ou données manquantes :", commande)
    except Exception as e:
        print(f"Erreur WooCommerce : {str(e)}")

# 🔹 Exécution du test local
if __name__ == "__main__":
    tester_derniere_commandes()