import pandas as pd
import numpy as np
import os
import re
from datetime import datetime, date
import matplotlib.pyplot as plt
from scipy.stats import norm

# Constants
CONTRACT_SIZE = 100

def get_spot_price(file_path):
    """Extracts the spot price from the CBOE CSV file."""
    with open(file_path, 'r') as f:
        lines = f.readlines()
        if len(lines) < 2: return None
        line2 = lines[1]
        match = re.search(r'Last: ([\d\.]+)', line2)
        if match:
            return float(match.group(1))
    return None

def load_cboe_data(file_path):
    """Parses the CBOE option chain CSV."""
    df = pd.read_csv(file_path, skiprows=3)
    cols = [
        'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net', 'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
        'Strike',
        'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask', 'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
    ]
    df.columns = cols
    
    # Convert numeric columns
    numeric_cols = ['Call IV', 'Call Delta', 'Call Gamma', 'Call OI', 'Strike', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    df['Expiration Date'] = pd.to_datetime(df['Expiration Date'], errors='coerce')
    
    # Filter rows with zero OI on both sides to speed up
    df = df[(df['Call OI'] > 0) | (df['Put OI'] > 0)].copy()
    
    return df

def calculate_gex_at_spot(df, spot_price):
    """Calculates Gamma Exposure (GEX) at the current spot price using provided Gamma."""
    df['Call GEX'] = df['Call Gamma'] * CONTRACT_SIZE * df['Call OI'] * (spot_price ** 2) * 0.01
    df['Put GEX'] = df['Put Gamma'] * CONTRACT_SIZE * df['Put OI'] * (spot_price ** 2) * 0.01 * (-1)
    df['Total GEX'] = df['Call GEX'] + df['Put GEX']
    return df

def vectorized_bs_gamma(S_levels, K, T, sigma, r=0.0, q=0.0):
    """
    Calculates BS Gamma for a range of Spot levels.
    S_levels: numpy array of spot prices
    K: Strike
    T: Time to expiry
    sigma: Volatility
    """
    K = np.array(K)[:, np.newaxis]
    T = np.array(T)[:, np.newaxis]
    sigma = np.array(sigma)[:, np.newaxis]
    S = S_levels[np.newaxis, :]
    
    # Avoid div by zero
    sigma = np.where(sigma <= 0, 1e-9, sigma)
    T = np.where(T <= 0, 1e-9, T)
    
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def get_gamma_profile(df, spot_price, price_range_pct=0.1, n_points=100):
    """Calculates the Total GEX across a range of spot prices using vectorized BS."""
    # Assuming "today" is Jan 14, 2026 based on the data
    csv_date = date(2026, 1, 14)
    
    df = df.copy()
    df['T'] = (df['Expiration Date'].dt.date - csv_date).apply(lambda x: x.days) / 365.0
    df['T'] = df['T'].clip(lower=1/365.0)
    
    levels = np.linspace(spot_price * (1 - price_range_pct), spot_price * (1 + price_range_pct), n_points)
    
    # Calls
    call_gammas = vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Call IV'])
    call_gex = (call_gammas * (df['Call OI'].values[:, np.newaxis]) * CONTRACT_SIZE * (levels**2) * 0.01).sum(axis=0)
    
    # Puts
    put_gammas = vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Put IV'])
    put_gex = (put_gammas * (df['Put OI'].values[:, np.newaxis]) * CONTRACT_SIZE * (levels**2) * 0.01 * (-1)).sum(axis=0)
    
    total_profile = call_gex + put_gex
    return levels, total_profile

def plot_gamma_profile(levels, profile, spot_price, zero_gamma, total_gex_spot):
    plt.figure(figsize=(12, 7))
    plt.plot(levels, profile / 1e9, label='Gamma Exposure', color='blue', linewidth=2)
    plt.axhline(0, color='black', linestyle='--', alpha=0.5)
    plt.axvline(spot_price, color='red', linestyle='-', label=f'Spot Price ({spot_price:.2f})')
    
    if zero_gamma:
        plt.axvline(zero_gamma, color='green', linestyle='--', label=f'Zero Gamma ({zero_gamma:.2f})')
        plt.scatter([zero_gamma], [0], color='green', zorder=5)
        
    plt.scatter([spot_price], [total_gex_spot / 1e9], color='red', zorder=5)
    
    plt.title('SPX Gamma Exposure Profile', fontsize=14)
    plt.xlabel('Index Level', fontsize=12)
    plt.ylabel('Total Gamma Exposure ($ Billions / 1%)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Shading
    plt.fill_between(levels, 0, profile / 1e9, where=(profile > 0), color='green', alpha=0.1)
    plt.fill_between(levels, 0, profile / 1e9, where=(profile < 0), color='red', alpha=0.1)
    
    output_dir = 'output'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    plt.savefig(os.path.join(output_dir, 'gamma_profile.png'))
    print(f"Plot saved to {os.path.join(output_dir, 'gamma_profile.png')}")

if __name__ == "__main__":
    csv_path = r'c:\projet\open-gamma\data\parquet_spx\spx_quotedata.csv'
    
    spot = get_spot_price(csv_path)
    if not spot:
        print("Could not find spot price.")
        exit()
        
    print(f"Current Spot Price: {spot}")
    
    df = load_cboe_data(csv_path)
    df_with_gex = calculate_gex_at_spot(df, spot)
    
    total_gex_spot = df_with_gex['Total GEX'].sum()
    print(f"Total Spot GEX: ${total_gex_spot/1e9:.2f} Billion")
    
    print("Calculating Gamma Profile...")
    levels, profile = get_gamma_profile(df, spot)
    
    # Find zero gamma level
    zero_gamma_level = None
    for i in range(len(profile)-1):
        if (profile[i] < 0 and profile[i+1] > 0) or (profile[i] > 0 and profile[i+1] < 0):
            zero_gamma_level = levels[i] - profile[i] * (levels[i+1] - levels[i]) / (profile[i+1] - profile[i])
            break
            
    if zero_gamma_level:
        print(f"Approximate Zero Gamma Level: {zero_gamma_level:.2f}")
    else:
        print("Zero Gamma Level not found in range.")
        
    print("Generating plot...")
    plot_gamma_profile(levels, profile, spot, zero_gamma_level, total_gex_spot)
