from woocommerce import API
from openai import OpenAI
import os
from dotenv import load_dotenv

# Charger variables .env
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

wcapi = API(
    url=os.getenv("WC_URL"),
    consumer_key=os.getenv("WC_CONSUMER_KEY"),
    consumer_secret=os.getenv("WC_CONSUMER_SECRET"),
    version="wc/v3",
    verify_ssl=True
)

def repondre_client(question):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "Tu es un assistant WooCommerce. Réponds clairement et poliment."},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erreur OpenAI : {str(e)}"

def tester_derniere_commandes():
    try:
        response = wcapi.get("orders", params={"per_page": 5})
        commandes = response.json()

        if isinstance(commandes, dict) and "code" in commandes:
            print("Erreur WooCommerce :", commandes)
            return

        for cmd in commandes:
            if "id" in cmd:
                question = f"Quel est le statut de la commande #{cmd['id']} ?"
                print(repondre_client(question))

    except Exception as e:
        print("Erreur :", e)

if __name__ == "__main__":
    tester_derniere_commandes()