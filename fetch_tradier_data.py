import requests
import pandas as pd
import json
import os

# ==========================================================
# CONFIGURATION TRADIER
# ==========================================================
# 1. Ouvrez un compte gratuit sur https://tradier.com/
# 2. Une fois connecté, allez sur https://dash.tradier.com/settings/api
# 3. Copiez votre "Access Token" ci-dessous :
TRADIER_TOKEN = "VOTRE_TOKEN_ICI"

# Utilisez 'https://api.tradier.com/v1/' pour le compte réel (même avec 0€)
# Ou 'https://sandbox.tradier.com/v1/' pour tester si vous n'avez pas encore de compte validé
BASE_URL = "https://api.tradier.com/v1/"

HEADERS = {
    'Authorization': f'Bearer {TRADIER_TOKEN}',
    'Accept': 'application/json'
}

def get_spot_price(symbol):
    """Récupère le prix actuel du sous-jacent (ex: SPY)"""
    url = f"{BASE_URL}markets/quotes"
    params = {'symbols': symbol}
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            # Tradier peut retourner un seul objet ou une liste selon le nombre de symboles
            quote = data['quotes']['quote']
            return float(quote['last']) if isinstance(quote, dict) else float(quote[0]['last'])
        else:
            print(f"[ERREUR SPOT] Code {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[EXCEPTION SPOT] {e}")
        return None

def get_expirations(symbol):
    """Récupère les dates d'expiration disponibles"""
    url = f"{BASE_URL}markets/options/expirations"
    params = {'symbol': symbol, 'includeAllRoots': 'true'}
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            return data['expirations']['date']
        return []
    except Exception as e:
        print(f"[EXCEPTION EXP] {e}")
        return []

def get_option_chain(symbol, expiration):
    """Récupère toute la chaîne d'options avec les Grecs pour une date donnée"""
    url = f"{BASE_URL}markets/options/chains"
    params = {
        'symbol': symbol,
        'expiration': expiration,
        'greeks': 'true' # INDISPENSABLE POUR VOTRE ANALYSE GAMMA/CHARM
    }
    try:
        response = requests.get(url, params=params, headers=HEADERS)
        
        if response.status_code == 200:
            data = response.json()
            options_list = data['options']['option']
            
            # Conversion en DataFrame
            df = pd.DataFrame(options_list)
            
            # Extraction des Grecs qui sont dans une colonne 'greeks' (dictionnaire)
            if 'greeks' in df.columns:
                greeks_df = pd.json_normalize(df['greeks'])
                df = pd.concat([df.drop('greeks', axis=1), greeks_df], axis=1)
            
            return df
        else:
            print(f"[ERREUR CHAIN] Code {response.status_code}: {response.text}")
            return None
    except Exception as e:
        print(f"[EXCEPTION CHAIN] {e}")
        return None

def main():
    SYMBOL = "SPY"
    
    print("="*60)
    print(f"RÉCUPÉRATION DE DONNÉES TRADIER POUR {SYMBOL}")
    print("="*60)
    
    if TRADIER_TOKEN == "VOTRE_TOKEN_ICI":
        print("\n[!] ATTENTION : Vous devez insérer votre Token Tradier dans le script.")
        print("Allez sur https://dash.tradier.com/settings/api pour le récupérer.")
        return

    # 1. Récupération du prix Spot
    print(f"\n[1/3] Récupération du prix spot pour {SYMBOL}...")
    spot = get_spot_price(SYMBOL)
    
    if spot:
        print(f" -> Prix {SYMBOL} actuel : ${spot:.2f}")
        
        # 2. Récupération des expirations
        print(f"\n[2/3] Recherche des dates d'expiration...")
        exps = get_expirations(SYMBOL)
        
        if exps:
            # On prend la première (0DTE ou prochaine échéance)
            target_exp = exps[0]
            print(f" -> Prochaine expiration trouvée : {target_exp}")
            
            # 3. Récupération de la chaîne complète avec les Grecs
            print(f"\n[3/3] Téléchargement de la chaîne d'options pour le {target_exp}...")
            df = get_option_chain(SYMBOL, target_exp)
            
            if df is not None:
                print(f" -> [SUCCÈS] {len(df)} contrats récupérés avec les Grecs.")
                
                # Sélection des colonnes pertinentes pour le Gamma/Charm
                cols_to_show = ['symbol', 'strike', 'option_type', 'open_interest', 'gamma', 'delta', 'theta']
                # Filtrage pour ne garder que les colonnes existantes
                existing_cols = [c for c in cols_to_show if c in df.columns]
                
                print("\nExtrait des données (Colonnes Alpha) :")
                print(df[existing_cols].head())
                
                # Sauvegarde au format CSV pour votre analyse
                filename = f"tradier_{SYMBOL}_{target_exp}.csv"
                df.to_csv(filename, index=False)
                print(f"\n[OK] Données sauvegardées dans : {filename}")
                
                # Calcul rapide du Gamma Total (Exemple)
                if 'gamma' in df.columns and 'open_interest' in df.columns:
                    # On s'assure que les types sont numériques
                    df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0)
                    df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)
                    total_gamma = (df['gamma'] * df['open_interest']).sum()
                    print(f" -> Gamma Total estimé pour cette échéance : {total_gamma:.4f}")

        else:
            print(" [!] Aucune date d'expiration trouvée.")
    else:
        print(" [!] Impossible de récupérer le prix spot. Vérifiez votre Token.")

if __name__ == "__main__":
    main()
