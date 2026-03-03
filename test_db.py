import mysql.connector

print("--- Tentative de connexion lancée ---")

try:
    conn = mysql.connector.connect(
        host="sql1270.main-hosting.eu", 
        user="u637875669_xOcRm",
        password="billykeke1234K@#", # Corrigé selon ta capture 504
        database="u637875669_mAofs"
    )

    if conn.is_connected():
        print("✅ Bravo ! La connexion à Hostinger est réussie.")
        cursor = conn.cursor()
        # On vérifie le nom de la boutique
        cursor.execute("SELECT option_value FROM wp_options WHERE option_name = 'blogname'")
        resultat = cursor.fetchone()
        print(f"Boutique connectée : {resultat[0]}")
        conn.close()

except Exception as e:
    print(f"❌ Échec : {e}")