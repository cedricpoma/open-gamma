"""
Script de récupération automatique des données SPX
À exécuter via Windows Task Scheduler chaque jour à 21h55 (heure française)
"""
import os
import sys
import asyncio
import pandas as pd
from datetime import date, datetime
from dotenv import load_dotenv

# Ajouter le chemin du projet
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

from main_live import create_manual_session, TARGET_SYMBOL
from tastytrade.instruments import NestedOptionChain
from tastytrade.dxfeed import Quote, Greeks, Summary
from tastytrade import DXLinkStreamer

load_dotenv()

async def fetch_and_save():
    """Récupère les données live et les sauvegarde en CSV."""
    username = os.getenv("TASTY_USERNAME")
    password = os.getenv("TASTY_PASSWORD")
    
    if not username or not password:
        print("[ERROR] Credentials missing in .env")
        return False
    
    print(f"[{datetime.now()}] Starting scheduled data fetch...")
    
    # 1. Auth
    session = create_manual_session(username, password)
    if not session:
        print("[ERROR] Authentication failed")
        return False
    
    # 2. Get Chain
    chains = NestedOptionChain.get(session, TARGET_SYMBOL)
    if not chains:
        print(f"[ERROR] No chains found for {TARGET_SYMBOL}")
        return False
    
    chain = chains[0]
    
    # 3. Filter expirations (0-60 days)
    target_expirations = [e for e in chain.expirations if 0 <= (e.expiration_date - date.today()).days < 60]
    
    streamer_symbols = []
    for exp in target_expirations:
        for strike in exp.strikes:
            streamer_symbols.append(strike.call_streamer_symbol)
            streamer_symbols.append(strike.put_streamer_symbol)
    
    spot_symbol = TARGET_SYMBOL
    cache = {'quotes': {}, 'greeks': {}, 'summaries': {}}
    
    # 4. Stream data
    print(f"[INFO] Subscribing to {len(streamer_symbols)} symbols...")
    
    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Quote, [spot_symbol])
        await streamer.subscribe(Greeks, streamer_symbols)
        await streamer.subscribe(Summary, streamer_symbols)
        
        # Poll for 15 seconds
        start = asyncio.get_running_loop().time()
        # Poll for 30 seconds to ensure full chain coverage
        start = asyncio.get_running_loop().time()
        while (asyncio.get_running_loop().time() - start) < 30.0:
            q = streamer.get_event_nowait(Quote)
            if q: cache['quotes'][q.event_symbol] = q
            
            g = streamer.get_event_nowait(Greeks)
            if g: cache['greeks'][g.event_symbol] = g
            
            s = streamer.get_event_nowait(Summary)
            if s: cache['summaries'][s.event_symbol] = s
            
            await asyncio.sleep(0.01)
    
    # 5. Get spot price
    current_spot = 0.0
    if spot_symbol in cache['quotes']:
        q = cache['quotes'][spot_symbol]
        bid = float(q.bid_price) if q.bid_price else 0.0
        ask = float(q.ask_price) if q.ask_price else 0.0
        current_spot = bid if bid > 0 else ask
    
    print(f"[INFO] Spot: {current_spot}, Greeks: {len(cache['greeks'])}, Summaries: {len(cache['summaries'])}")
    
    # 6. Build DataFrame
    data_rows = []
    for exp in target_expirations:
        for strike in exp.strikes:
            c_s = strike.call_streamer_symbol
            p_s = strike.put_streamer_symbol
            
            c_g = cache['greeks'].get(c_s)
            c_sum = cache['summaries'].get(c_s)
            p_g = cache['greeks'].get(p_s)
            p_sum = cache['summaries'].get(p_s)
            
            c_oi = c_sum.open_interest if c_sum else 0
            p_oi = p_sum.open_interest if p_sum else 0
            
            if c_oi > 0 or p_oi > 0:
                data_rows.append({
                    'Expiration Date': exp.expiration_date,
                    'Strike': strike.strike_price,
                    'Call Gamma': c_g.gamma if c_g else 0,
                    'Call Delta': c_g.delta if c_g else 0,
                    'Call IV': c_g.volatility if c_g else 0,
                    'Call OI': c_oi,
                    'Put Gamma': p_g.gamma if p_g else 0,
                    'Put Delta': p_g.delta if p_g else 0,
                    'Put IV': p_g.volatility if p_g else 0,
                    'Put OI': p_oi
                })
    
    df = pd.DataFrame(data_rows)
    
    if df.empty:
        print("[ERROR] No data collected")
        return False
    
    # 7. Save to CSV - Convert to CBOE format (22 columns)
    save_dir = 'data/parquet_spx'
    os.makedirs(save_dir, exist_ok=True)
    
    # Define CBOE column structure
    cboe_cols = [
        'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net', 'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
        'Strike',
        'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask', 'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
    ]
    
    # Add missing columns with 0 or empty string
    for col in cboe_cols:
        if col not in df.columns:
            df[col] = 0
    
    # Reorder columns to match CBOE format
    df_cboe = df[cboe_cols]
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'{save_dir}/spx_live_{timestamp}.csv'
    latest_filename = f'{save_dir}/spx_quotedata.csv'
    
    header_lines = [
        "SPX Options Data (Scheduled Fetch)",
        f"S&P 500 INDEX,Last: {current_spot},Change: 0",
        f"Date: {date.today().strftime('%a %b %d %Y')}"
    ]
    
    for filename in [csv_filename, latest_filename]:
        with open(filename, 'w', newline='') as f:
            f.write('\n'.join(header_lines) + '\n')
            df_cboe.to_csv(f, index=False)
    
    print(f"[SUCCESS] Saved {len(df_cboe)} rows to {csv_filename}")
    print(f"[SUCCESS] Updated {latest_filename}")
    
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(fetch_and_save())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
