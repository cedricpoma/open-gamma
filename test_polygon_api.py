import requests
import json
import os

# Clé API fournie par l'utilisateur
API_KEY = "8_qZTw25w7xtkqf6CXWE0GNoI2_QjwWX"
SYMBOL = "SPY"

def test_polygon_api():
    print(f"=== TEST API POLYGON.IO ===")
    print(f"Symbole teste : {SYMBOL}")
    
    # 1. Tester la fiche de base (TICKER)
    print("\n[1/2] Test du Snapshot Options (Chain)...")
    url = f"https://api.polygon.io/v3/snapshot/options/{SYMBOL}?apiKey={API_KEY}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            print(f"[OK] Succès ! Nombre d'options trouvées : {len(results)}")
            if len(results) > 0:
                print("Détails du premier contrat trouvé :")
                # On affiche un extrait pour voir si les Grecs sont dedans
                sample = results[0]
                print(json.dumps(sample, indent=2))
        else:
            print(f"[ERREUR] Code {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[ERREUR EXCEPTION] : {e}")

    # 2. Tester le Last Quote pour le prix spot
    print("\n[2/4] Test du prix Spot (Last Quote)...")
    url_spot = f"https://api.polygon.io/v2/last/nbbo/{SYMBOL}?apiKey={API_KEY}"
    try:
        response = requests.get(url_spot)
        if response.status_code == 200:
            print(f"[OK] Prix Spot récupéré : {response.json().get('results', {}).get('p')}")
        else:
            print(f"[ERREUR] Code {response.status_code}")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    test_polygon_api()
