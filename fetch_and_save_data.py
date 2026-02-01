#!/usr/bin/env python3
"""
Script pour récupérer les données d'Alpha Vantage et les sauvegarder en parquet
"""

import pandas as pd
from alpha_vantage.options import Options
from alpha_vantage.timeseries import TimeSeries
from datetime import datetime
import os

# Votre clé API
API_KEY = 'A85Z12K4YSI3BC5D'

import time

def fetch_and_save_options_data(symbol='SPY', output_dir='data/parquet_spy'):
    """
    Récupère les données d'options depuis Alpha Vantage et les sauvegarde en parquet
    """
    print(f"[INFO] Recuperation des donnees pour {symbol}...")
    
    # Créer le dossier si nécessaire
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # 1. Récupérer le prix spot
        print("[INFO] Recuperation du prix spot...")
        try:
            ts = TimeSeries(key=API_KEY)
            price_data, _ = ts.get_quote_endpoint(symbol=symbol)
            if price_data and '05. price' in price_data:
                spot_price = float(price_data['05. price'])
                print(f"   Prix {symbol}: ${spot_price:.2f}")
            else:
                print(f"   [WARN] Reponse API incomplete pour le prix spot: {price_data}")
        except Exception as e:
            print(f"   [WARN] Impossible de recuperer le prix spot: {e}")

        # Sleep to avoid rate limit (1 request per second)
        print("[INFO] Attente de 2 secondes pour respecter le rate limit...")
        time.sleep(2)

        # 2. Récupérer les options
        print("[INFO] Recuperation des options...")
        options_client = Options(key=API_KEY)
        data, meta_data = options_client.get_realtime_options(symbol=symbol)
        
        if data is None or data.empty:
            print("[ERROR] Aucune donnee recue (Empty DataFrame)")
            return None

        print(f"   [OK] Recupere {len(data)} options")
        
        # 3. Sauvegarder en parquet
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_file = f"{output_dir}/{date_str}.parquet"
        
        # Convert objects to appropriate types to avoid parquet issues
        for col in data.columns:
            if data[col].dtype == 'object':
                try:
                    data[col] = pd.to_numeric(data[col])
                except:
                    pass

        data.to_parquet(output_file, index=False)
        print(f"\n[OK] Donnees sauvegardees: {output_file}")
        
        # 4. Afficher les statistiques
        print(f"\n[INFO] Statistiques:")
        print(f"   - Nombre total d'options: {len(data)}")
        print(f"   - Colonnes: {len(data.columns)}")
        print(f"   - Taille du fichier: {os.path.getsize(output_file) / 1024:.2f} KB")
        
        return data
        
    except Exception as e:
        print(f"[ERROR] Erreur critique lors de la recuperation: {e}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("RECUPERATION DE DONNEES ALPHA VANTAGE")
    print("=" * 60)
    print()
    
    data = fetch_and_save_options_data()
    
    if data is not None:
        print("\n[OK] Operation reussie!")
    else:
        print("\n[ERROR] Echec de la recuperation")
