import mysql.connector

try:
    # Connexion avec les informations réelles de ton fichier wp-config.php
    conn = mysql.connector.connect(
        host="sql1270.main-hosting.eu", # Identifié via srv1270 dans ton URL Hostinger
        user="u637875669_xOcRm",        # Confirmé par ton wp-config.php
        password="kekebilly1234K@#",         # Le mot de passe exact de ta capture d'écran
        database="u637875669_mAofs"     # Le nom exact de ta base de données
    )

    if conn.is_connected():
        print("✅ Bravo ! La connexion à Hostinger est réussie.")
        
        # Test de lecture du nom de ta boutique
        cursor = conn.cursor()
        cursor.execute("SELECT option_value FROM wp_options WHERE option_name = 'blogname'")
        nom_site = cursor.fetchone()
        
        if nom_site:
            print(f"Boutique connectée : {nom_site[0]}")
        else:
            print("Connexion établie, mais impossible de lire les données (vérifie le préfixe wp_).")
        
        conn.close()

except Exception as e:
    print(f"❌ Échec du test : {e}")
    print("\nPROCHAINE ÉTAPE SI ÇA ÉCHOUE :")
    print("Ton adresse IP doit être autorisée dans la section 'Remote MySQL' de ton panel Hostinger.")