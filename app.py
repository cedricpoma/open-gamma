from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, date
import os
import asyncio
from gamma_engine import GammaEngine

# Import live fetch components
try:
    from main_live import create_manual_session, TARGET_SYMBOL
    from tastytrade.instruments import NestedOptionChain
    from tastytrade.dxfeed import Quote, Greeks, Summary
    from tastytrade import DXLinkStreamer
except Exception as e:
    print(f"!!! IMPORT ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
    create_manual_session = None

print(f"[DEBUG] Import Check: create_manual_session is {'AVAILABLE' if create_manual_session else 'MISSING'}", flush=True)

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

engine = GammaEngine()

def get_engine_data():
    """Helper to prepare all engine data for the frontend."""
    if engine.options_df is None:
        return None
    
    # Increase range to 10% for better view
    levels_gamma, total_gamma = engine.get_gamma_profile(price_range_pct=0.1, n_points=100)
    zero_gamma = engine.find_zero_gamma(levels_gamma, total_gamma)
    
    # 2. Charm Profile
    charm_data = engine.get_charm_profile(price_range_pct=0.1, n_points=100)
    
    # 3. Strike Breakdown (Strikes near spot)
    df = engine.options_df.copy()
    df['Total GEX'] = (df['Call Gamma'] * df['Call OI'] - df['Put Gamma'] * df['Put OI']) * engine.contract_size * (engine.spot_price**2) * 0.01
    df['Call GEX'] = df['Call Gamma'] * df['Call OI'] * engine.contract_size * (engine.spot_price**2) * 0.01
    df['Put GEX'] = -df['Put Gamma'] * df['Put OI'] * engine.contract_size * (engine.spot_price**2) * 0.01
    
    strike_summary = df.groupby('Strike').agg({
        'Total GEX': 'sum',
        'Call GEX': 'sum',
        'Put GEX': 'sum',
        'Call OI': 'sum',
        'Put OI': 'sum'
    }).reset_index()
    
    # Filter for active strikes near spot (+/- 15% to be safe)
    strike_summary = strike_summary[
        (strike_summary['Strike'] >= engine.spot_price * 0.85) & 
        (strike_summary['Strike'] <= engine.spot_price * 1.15)
    ]
    strike_summary = strike_summary.sort_values('Strike')
    
    # Calculate Put/Call Ratio
    strike_summary['PC_Ratio'] = strike_summary.apply(
        lambda row: row['Put OI'] / row['Call OI'] if row['Call OI'] > 0 else 0, axis=1
    )
    
    # Debug strike breakdown
    if not strike_summary.empty:
        pos_gex = len(strike_summary[strike_summary['Total GEX'] > 0])
        neg_gex = len(strike_summary[strike_summary['Total GEX'] < 0])
        print(f"[STRIKE DEBUG] Min Strike: {strike_summary['Strike'].min()}, Max Strike: {strike_summary['Strike'].max()}", flush=True)
        print(f"[STRIKE DEBUG] Positive GEX strikes: {pos_gex}, Negative GEX strikes: {neg_gex}", flush=True)
    else:
        print("[STRIKE DEBUG] strike_summary is EMPTY!", flush=True)
    
    # 4. GEX by Expiration
    df['Expiration Date'] = pd.to_datetime(df['Expiration Date'])
    today = pd.Timestamp.now().normalize()
    df['DTE'] = (df['Expiration Date'] - today).dt.days
    
    exp_summary = df.groupby('Expiration Date').agg({
        'Total GEX': 'sum',
        'Call OI': 'sum',
        'Put OI': 'sum',
        'DTE': 'first'
    }).reset_index()
    exp_summary = exp_summary.sort_values('Expiration Date')
    
    # Categorize expirations
    def categorize_exp(dte):
        if dte == 0: return '0DTE'
        elif dte == 1: return '1DTE'
        elif dte <= 7: return 'Weekly'
        elif dte <= 30: return 'Monthly'
        else: return 'Quarterly+'
    
    exp_summary['Category'] = exp_summary['DTE'].apply(categorize_exp)
    
    # 5. GEX Levels (Key Support/Resistance)
    max_pos_gex_idx = strike_summary['Total GEX'].idxmax() if not strike_summary.empty else None
    max_neg_gex_idx = strike_summary['Total GEX'].idxmin() if not strike_summary.empty else None
    
    gex_levels = {
        "zero_gamma": float(zero_gamma) if zero_gamma else None,
        "max_positive_strike": float(strike_summary.loc[max_pos_gex_idx, 'Strike']) if max_pos_gex_idx is not None else None,
        "max_positive_gex": float(strike_summary.loc[max_pos_gex_idx, 'Total GEX']) if max_pos_gex_idx is not None else None,
        "max_negative_strike": float(strike_summary.loc[max_neg_gex_idx, 'Strike']) if max_neg_gex_idx is not None else None,
        "max_negative_gex": float(strike_summary.loc[max_neg_gex_idx, 'Total GEX']) if max_neg_gex_idx is not None else None,
    }
    
    # 6. OI Heatmap Data (Strike x Expiration)
    oi_pivot = df.pivot_table(
        index='Strike',
        columns='Expiration Date',
        values=['Call OI', 'Put OI'],
        aggfunc='sum',
        fill_value=0
    )
    
    # Filter strikes near spot for heatmap
    oi_strikes = [s for s in oi_pivot.index if engine.spot_price * 0.95 <= s <= engine.spot_price * 1.05]
    oi_exps = sorted(df['Expiration Date'].unique())[:10]  # Top 10 expirations
    
    oi_heatmap_data = []
    for strike in oi_strikes:
        for exp in oi_exps:
            try:
                call_oi = float(oi_pivot.loc[strike, ('Call OI', exp)]) if ('Call OI', exp) in oi_pivot.columns else 0
                put_oi = float(oi_pivot.loc[strike, ('Put OI', exp)]) if ('Put OI', exp) in oi_pivot.columns else 0
                oi_heatmap_data.append({
                    'strike': float(strike),
                    'expiration': exp.strftime('%Y-%m-%d') if hasattr(exp, 'strftime') else str(exp),
                    'call_oi': call_oi,
                    'put_oi': put_oi,
                    'total_oi': call_oi + put_oi
                })
            except:
                pass

    # 7. IV Stats (ATM Implied Volatility)
    atm_range = 0.02  # ±2% from spot
    atm_mask = (df['Strike'] >= engine.spot_price * (1 - atm_range)) & (df['Strike'] <= engine.spot_price * (1 + atm_range))
    atm_df = df[atm_mask]
    
    # OI-weighted average IV near the money
    call_oi_sum = atm_df['Call OI'].sum()
    put_oi_sum = atm_df['Put OI'].sum()
    
    atm_call_iv = float((atm_df['Call IV'] * atm_df['Call OI']).sum() / call_oi_sum) if call_oi_sum > 0 else 0.0
    atm_put_iv = float((atm_df['Put IV'] * atm_df['Put OI']).sum() / put_oi_sum) if put_oi_sum > 0 else 0.0
    atm_iv = (atm_call_iv + atm_put_iv) / 2.0 if (atm_call_iv > 0 and atm_put_iv > 0) else max(atm_call_iv, atm_put_iv)
    
    # IV Skew: difference between OTM Put IV (below spot) and OTM Call IV (above spot)
    otm_put_mask = (df['Strike'] < engine.spot_price * 0.98) & (df['Strike'] >= engine.spot_price * 0.93) & (df['Put IV'] > 0)
    otm_call_mask = (df['Strike'] > engine.spot_price * 1.02) & (df['Strike'] <= engine.spot_price * 1.07) & (df['Call IV'] > 0)
    
    otm_put_iv = float(df.loc[otm_put_mask, 'Put IV'].mean()) if otm_put_mask.any() else 0.0
    otm_call_iv = float(df.loc[otm_call_mask, 'Call IV'].mean()) if otm_call_mask.any() else 0.0
    iv_skew = otm_put_iv - otm_call_iv
    
    iv_stats = {
        "atm_iv": atm_iv,
        "call_iv_mean": atm_call_iv,
        "put_iv_mean": atm_put_iv,
        "skew": iv_skew
    }
    
    # 8. IV Smile (Call IV & Put IV by Strike)
    smile_mask = (strike_summary['Strike'] >= engine.spot_price * 0.93) & (strike_summary['Strike'] <= engine.spot_price * 1.07)
    smile_strikes = strike_summary.loc[smile_mask, 'Strike'].values
    
    iv_smile_data = []
    for s in smile_strikes:
        s_df = df[df['Strike'] == s]
        c_iv = float(s_df.loc[s_df['Call IV'] > 0, 'Call IV'].mean()) if (s_df['Call IV'] > 0).any() else None
        p_iv = float(s_df.loc[s_df['Put IV'] > 0, 'Put IV'].mean()) if (s_df['Put IV'] > 0).any() else None
        if c_iv or p_iv:
            iv_smile_data.append({"strike": float(s), "call_iv": c_iv, "put_iv": p_iv})
    
    # 9. IV Term Structure (Average IV by DTE)
    iv_term = df[df['Call IV'] > 0].groupby('Expiration Date').agg({
        'Call IV': 'mean',
        'Put IV': 'mean',
        'DTE': 'first'
    }).reset_index()
    iv_term = iv_term.sort_values('DTE')
    iv_term['Avg IV'] = (iv_term['Call IV'] + iv_term['Put IV']) / 2.0
    
    iv_term_data = [
        {
            "expiration": row['Expiration Date'].strftime('%Y-%m-%d') if hasattr(row['Expiration Date'], 'strftime') else str(row['Expiration Date']),
            "dte": int(row['DTE']),
            "avg_iv": float(row['Avg IV']),
            "call_iv": float(row['Call IV']),
            "put_iv": float(row['Put IV'])
        } for _, row in iv_term.iterrows()
    ]

    return {
        "spot_price": float(engine.spot_price),
        "data_date": str(engine.data_date),
        "zero_gamma": float(zero_gamma) if zero_gamma else None,
        "gamma_profile": [
            {"price": float(p), "gex": float(g)} for p, g in zip(levels_gamma, total_gamma)
        ],
        "charm_profile": {
            "net": [{"price": float(p), "charm": float(c)} for p, c in zip(charm_data['levels'], charm_data['net_charm'])],
            "call": [{"price": float(p), "charm": float(c)} for p, c in zip(charm_data['levels'], charm_data['call_charm'])],
            "put": [{"price": float(p), "charm": float(c)} for p, c in zip(charm_data['levels'], charm_data['put_charm'])]
        },
        "vanna_profile": {
            "net": [{"price": float(p), "vanna": float(v)} for p, v in zip(engine.get_vanna_profile()['levels'], engine.get_vanna_profile()['net'])]
        },
        "delta_profile": {
            "net": [{"price": float(p), "delta": float(d)} for p, d in zip(engine.get_delta_profile()['levels'], engine.get_delta_profile()['net'])]
        },
        "speed_profile": {
            "net": [{"price": float(p), "speed": float(s)} for p, s in zip(engine.get_speed_profile()['levels'], engine.get_speed_profile()['net'])]
        },

        "strike_breakdown": strike_summary.to_dict(orient="records"),
        "gex_levels": gex_levels,
        "gex_by_expiration": [
            {
                "expiration": row['Expiration Date'].strftime('%Y-%m-%d') if hasattr(row['Expiration Date'], 'strftime') else str(row['Expiration Date']),
                "dte": int(row['DTE']),
                "category": row['Category'],
                "total_gex": float(row['Total GEX']),
                "call_oi": float(row['Call OI']),
                "put_oi": float(row['Put OI'])
            } for _, row in exp_summary.iterrows()
        ],
        "oi_heatmap": oi_heatmap_data,
        "iv_stats": iv_stats,
        "iv_smile": iv_smile_data,
        "iv_term_structure": iv_term_data
    }

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "running", 
        "engine_ready": engine.options_df is not None,
        "last_date": str(engine.data_date) if engine.data_date else None
    })

@app.route('/api/load-csv', methods=['POST'])
def load_csv():
    csv_path = request.json.get('path', 'data/parquet_spx/spx_quotedata.csv')
    if not os.path.exists(csv_path):
        return jsonify({"error": f"File {csv_path} not found"}), 404
    
    try:
        engine.load_cboe_csv(csv_path)
        return jsonify({
            "success": True, 
            "data": get_engine_data()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/fetch-live', methods=['POST'])
def fetch_live():
    """Triggers a live fetch from Tastytrade API (Updated Logic)."""
    print("[DEBUG] /api/fetch-live endpoint hit!", flush=True)
    try:
        if not create_manual_session:
            return jsonify({"error": "Live components not available (check main_live.py)"}), 500

        # Run async function in a new loop
        async def run_fetch():
            # 1. Authenticate via OAuth2
            session = create_manual_session()
            if not session:
                 raise Exception("Authentication failed - check OAuth2 credentials in .env")

            # 2. Fetch Chain
            chains = NestedOptionChain.get(session, TARGET_SYMBOL)
            if not chains:
                raise Exception(f"No chains found for {TARGET_SYMBOL}")
            chain = chains[0]

            # 3. Filter Symbols (0-60 days)
            streamer_symbols = []
            target_expirations = [e for e in chain.expirations if 0 <= (e.expiration_date - date.today()).days < 60]
            
            # Debug Chain Content
            all_strikes = []
            for exp in target_expirations:
                for s in exp.strikes:
                    all_strikes.append(float(s.strike_price))
            
            if all_strikes:
                print(f"[CHAIN DEBUG] Found {len(all_strikes)} strikes. Range: {min(all_strikes)} - {max(all_strikes)}", flush=True)
            else:
                print("[CHAIN DEBUG] No strikes found in chain!", flush=True)

            for exp in target_expirations:
                for strike in exp.strikes:
                    streamer_symbols.append(strike.call_streamer_symbol)
                    streamer_symbols.append(strike.put_streamer_symbol)
            
            # Spot Symbol
            spot_symbol = TARGET_SYMBOL
            if TARGET_SYMBOL == "SPX": spot_symbol = "SPX"

            # 4. Stream Data
            cache = {'quotes': {}, 'greeks': {}, 'summaries': {}}
            
            async with DXLinkStreamer(session) as streamer:
                await streamer.subscribe(Quote, [spot_symbol])
                await streamer.subscribe(Greeks, streamer_symbols)
                await streamer.subscribe(Summary, streamer_symbols)
                
                # Poll for 10 seconds
                start = asyncio.get_running_loop().time()
                # Poll for 25 seconds
                start = asyncio.get_running_loop().time()
                while (asyncio.get_running_loop().time() - start) < 25.0:
                    q = streamer.get_event_nowait(Quote)
                    if q: cache['quotes'][q.event_symbol] = q
                    
                    g = streamer.get_event_nowait(Greeks)
                    if g: cache['greeks'][g.event_symbol] = g
                    
                    s = streamer.get_event_nowait(Summary)
                    if s: cache['summaries'][s.event_symbol] = s
                    
                    await asyncio.sleep(0.01)

            # 5. Process Data
            current_spot = 0.0
            if spot_symbol in cache['quotes']:
                q = cache['quotes'][spot_symbol]
                bid = float(q.bid_price) if q.bid_price else 0.0
                ask = float(q.ask_price) if q.ask_price else 0.0
                current_spot = bid if (bid > 0) else ask
            
            print(f"[DEBUG] Cache sizes - Quotes: {len(cache['quotes'])}, Greeks: {len(cache['greeks'])}, Summaries: {len(cache['summaries'])}", flush=True)

            data_rows = []
            for exp in target_expirations:
                for strike in exp.strikes:
                    c_s = strike.call_streamer_symbol
                    p_s = strike.put_streamer_symbol
                    
                    c_g = cache['greeks'].get(c_s)
                    c_sum = cache['summaries'].get(c_s)
                    
                    c_gamma = c_g.gamma if c_g else 0
                    c_delta = c_g.delta if c_g else 0
                    c_iv = c_g.volatility if c_g else 0
                    c_oi = c_sum.open_interest if c_sum else 0
                    
                    p_g = cache['greeks'].get(p_s)
                    p_sum = cache['summaries'].get(p_s)
                    
                    p_gamma = p_g.gamma if p_g else 0
                    p_delta = p_g.delta if p_g else 0
                    p_iv = p_g.volatility if p_g else 0
                    p_oi = p_sum.open_interest if p_sum else 0
                    
                    # COMMENTED OUT FILTER TO FORCE DATA
                    # if c_oi > 0 or p_oi > 0:
                    data_rows.append({
                        'Expiration Date': exp.expiration_date,
                        'Strike': strike.strike_price,
                        'Call Gamma': c_gamma, 'Call Delta': c_delta, 'Call IV': c_iv, 'Call OI': c_oi,
                        'Put Gamma': p_gamma, 'Put Delta': p_delta, 'Put IV': p_iv, 'Put OI': p_oi
                    })
            
            # Debug Counts
            # n_calls = len(pd.DataFrame(data_rows)[pd.DataFrame(data_rows)['Call Gamma'] > 0]) if data_rows else 0
            # n_puts = len(pd.DataFrame(data_rows)[pd.DataFrame(data_rows)['Put Gamma'] > 0]) if data_rows else 0
            # print(f"[DEBUG] Valid Data Rows: {len(data_rows)} | Non-Zero Calls: {n_calls} | Non-Zero Puts: {n_puts}", flush=True)

            print(f"[DEBUG] Built DataFrame with {len(data_rows)} rows", flush=True)
            return pd.DataFrame(data_rows), current_spot

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            df, spot = loop.run_until_complete(run_fetch())
        finally:
            loop.close()

        if df is not None and not df.empty:
            if spot == 0:
                 # Fallback for Spot if missing (Pre-market or error)
                 spot = 6900.0 
            
            # AUTO-SAVE: Sauvegarder les données en CSV
            save_dir = 'data/parquet_spx'
            os.makedirs(save_dir, exist_ok=True)
            
            # Format dataframe to match CBOE structure strictly
            cboe_cols = [
                'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net', 'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
                'Strike',
                'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask', 'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
            ]
            
            # Add missing columns with 0 or empty
            for col in cboe_cols:
                if col not in df.columns:
                    df[col] = 0
            
            # Reorder columns
            df_cboe = df[cboe_cols]

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f'{save_dir}/spx_live_{timestamp}.csv'
            latest_filename = f'{save_dir}/spx_quotedata.csv'
            
            # Créer un header compatible CBOE pour réutilisation
            header_lines = [
                f"SPX Options Data (Live Fetch)",
                f"S&P 500 INDEX,Last: {spot},Change: 0",
                f"Date: {date.today().strftime('%a %b %d %Y')}"
            ]
            
            with open(csv_filename, 'w') as f:
                f.write('\n'.join(header_lines) + '\n')
                df_cboe.to_csv(f, index=False)
            
            # Copier aussi vers le fichier "latest"
            with open(latest_filename, 'w') as f:
                f.write('\n'.join(header_lines) + '\n')
                df_cboe.to_csv(f, index=False)
            
            print(f"[SAVE] Data saved to {csv_filename} and {latest_filename}", flush=True)
            
            engine.load_dataframe(df, spot, date.today())
            return jsonify({"success": True, "data": get_engine_data()})
        else:
            return jsonify({"error": "No data fetched"}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    data = get_engine_data()
    if data: return jsonify(data)
    return jsonify({"error": "No data loaded"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=8000)
