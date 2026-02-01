import os
import webbrowser
import asyncio
import pandas as pd
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
import httpx
from httpx import Client, AsyncClient

# Import from the installed library
from tastytrade import Session, DXLinkStreamer
from tastytrade.instruments import NestedOptionChain
from tastytrade.dxfeed import Quote, Greeks, Summary
from tastytrade import API_URL, API_VERSION
from tastytrade.utils import now_in_new_york

import logging

# Configure Logging for production (INFO level to see progress)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('tastytrade')
logger.setLevel(logging.INFO)

from gamma_engine import GammaEngine

# Load environment variables
load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")
TARGET_SYMBOL = os.getenv("TARGET_SYMBOL", "SPX")

def create_manual_session(username, password):
    """
    Manually creates a Session object to bypass potential library auth issues,
    using the method known to work in debug_auth_v2.py.
    """
    print(f"[AUTH] Manual connection for {username}...")
    try:
        # 1. Manual HTTP Request (Known to work)
        resp = httpx.post(
            "https://api.tastyworks.com/sessions",
            json={"login": username, "password": password, "remember-me": True},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=10
        )
        
        if resp.status_code != 201:
            print(f"[ERROR] Manual Login Failed: {resp.status_code} - {resp.text}")
            return None
            
        data = resp.json().get('data', {})
        session_token = data.get('session-token')
        
        if not session_token:
            print("[ERROR] No session-token returned.")
            return None
            
        print("[AUTH] Token received. Hydrating tastytrade.Session object...")
        
        # 2. Hydrate the tastytrade Session object
        # We bypass __init__ because it triggers its own login flow
        session = Session.__new__(Session)
        
        # Set attributes expected by the library
        session.session_token = session_token
        session.base_url = API_URL
        session.is_test = False
        session.proxy = None
        session.provider_secret = ""
        session.refresh_token = data.get('remember-token', '')
        
        # Clients
        headers = {
            "Accept": "application/json", 
            "Content-Type": "application/json",
            "Authorization": f"{session_token}",
            "Accept-Version": API_VERSION
        }
        
        session.client = Client(base_url=API_URL, headers=headers)
        session.sync_client = session.client
        session.async_client = AsyncClient(base_url=API_URL, headers=headers)
        # Some versions use a specific async client or request method, but usually 'client' is key.
        # We'll mock/set what we can.
        
        # Use library method for streamer tokens if possible, or do it manually if that fails
        # The library usually has methods like get_customer() which rely on the client.
        
        print("[AUTH] Validating Session and fetching Streamer tokens...")
        try:
            # We try to use the session to fetch streamer tokens. 
            # If the session object is set up correctly, this internal library call should work.
            # Introspecting the library: usually session.streamer_tokens or similar.
            # But let's try the library's standard way to 'refresh_streamer_tokens' if it exists
            # Or just fetch them manually and set them.
            
            # Manual fetch of streamer tokens to be safe
            t_resp = session.client.get("/api-quote-tokens")
            if t_resp.status_code == 200:
                token_data = t_resp.json()['data']
                # Depending on library version, we need to set these.
                # DXLinkStreamer(session) uses session.streamer_token presumably.
                # Let's inspect session object in a try/except or just set common props.
                session.streamer_token = token_data.get('token')
                session.dxlink_url = token_data.get('dxlink-url')
                session.streamer_url = token_data.get('streamer-url') # confusing naming in API sometimes
                
                print(f"[SUCCESS] Streamer Token: {session.streamer_token[:10]}...")
            else:
                print(f"[WARN] Could not fetch streamer tokens: {t_resp.status_code}")
                
        except Exception as e:
            print(f"[WARN] Error setting up streamer tokens: {e}")

        return session

    except Exception as e:
        print(f"[CRITICAL] Manual session creation error: {e}")
        return None

async def fetch_and_update_dashboard():
    """Single iteration: fetch live data and update dashboard."""
    if not USERNAME or not PASSWORD:
        print("[ERROR] Credentials missing in .env")
        return False

    # 1. Authenticate
    session = create_manual_session(USERNAME, PASSWORD)
    if not session:
        return False

    # 2. Fetch Chain
    print(f"[INFO] Fetching Chain for {TARGET_SYMBOL}...")
    try:
        # NestedOptionChain.get returns a list of chains
        chains = NestedOptionChain.get(session, TARGET_SYMBOL)
        if not chains:
            print(f"[ERROR] No chains found for {TARGET_SYMBOL}")
            return False
            
        # Usually for an equity/index like SPX, there is one main chain object returned
        chain = chains[0]
        print(f"[INFO] Chain received. Expirations: {len(chain.expirations)}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch chain: {e}")
        import traceback
        traceback.print_exc()
        print("Debugging Session State:", session.__dict__.keys())
        return False

    # 3. Filter Symbols
    streamer_symbols = []
    # usage: 0-60 days
    target_expirations = [e for e in chain.expirations if 0 <= (e.expiration_date - date.today()).days < 60]
    print(f"[INFO] Processing {len(target_expirations)} expirations...")

    for exp in target_expirations:
        for strike in exp.strikes:
            streamer_symbols.append(strike.call_streamer_symbol)
            streamer_symbols.append(strike.put_streamer_symbol)
            
    # Add Spot
    spot_symbol = TARGET_SYMBOL
    if TARGET_SYMBOL == "SPX":
        spot_symbol = "SPX" # or SPXWZ if needed, but SPX usually works for index quote

    print(f"[INFO] Subscribing to {len(streamer_symbols)} option symbols...")
    
    # 4. Stream Data
    data_rows = []
    current_spot = 0.0
    
    # Cache to store latest values
    cache = {
        'quotes': {},
        'greeks': {},
        'summaries': {}
    }
    
    # Verify Streamer Connection
    try:
        async with DXLinkStreamer(session) as streamer:
            print("[STREAM] Connected to DXLink.")
            
            # Subscribe
            print(f"[STREAM] Subscribing to {len(streamer_symbols)} symbols...")
            await streamer.subscribe(Quote, [spot_symbol])
            await streamer.subscribe(Greeks, streamer_symbols)
            await streamer.subscribe(Summary, streamer_symbols)
            
            print("[STREAM] Polling for data (30s)...")
            
            # Poll for events using get_event_nowait in a loop
            start = asyncio.get_event_loop().time()
            duration = 30.0
            poll_count = 0
            
            while (asyncio.get_event_loop().time() - start) < duration:
                # Try to get events without blocking
                q = streamer.get_event_nowait(Quote)
                if q:
                    cache['quotes'][q.event_symbol] = q
                    poll_count += 1
                
                g = streamer.get_event_nowait(Greeks)
                if g:
                    cache['greeks'][g.event_symbol] = g
                    poll_count += 1
                
                s = streamer.get_event_nowait(Summary)
                if s:
                    cache['summaries'][s.event_symbol] = s
                    poll_count += 1
                
                # Small sleep to avoid busy-waiting
                await asyncio.sleep(0.01)
            
            print(f"[INFO] Polling complete. Events processed: {poll_count}")
            print(f"[INFO] Data collected. Quotes: {len(cache['quotes'])}, Greeks: {len(cache['greeks'])}, Summaries: {len(cache['summaries'])}")

            # READ DATA FROM CACHE
            # Spot
            if spot_symbol in cache['quotes']:
                q = cache['quotes'][spot_symbol]
                # quote logic - convert Decimal to float
                bid = float(q.bid_price) if q.bid_price else 0.0
                ask = float(q.ask_price) if q.ask_price else 0.0
                current_spot = bid if (bid and bid > 0) else ask
                print(f"[DATA] Spot: {current_spot}")
            else:
                 print(f"[WARN] Spot symbol {spot_symbol} not found in quotes.")
            
            # Options
            print("[INFO] Compiling DataFrame...")
            for exp in target_expirations:
                # Optimized loop
                for strike in exp.strikes:
                    c_s = strike.call_streamer_symbol
                    p_s = strike.put_streamer_symbol
                    
                    # Extract Call
                    c_g = cache['greeks'].get(c_s)
                    c_sum = cache['summaries'].get(c_s)
                    
                    c_gamma = c_g.gamma if c_g else 0
                    c_delta = c_g.delta if c_g else 0
                    c_iv = c_g.volatility if c_g else 0
                    c_oi = c_sum.open_interest if c_sum else 0
                    
                    # Extract Put
                    p_g = cache['greeks'].get(p_s)
                    p_sum = cache['summaries'].get(p_s)
                    
                    p_gamma = p_g.gamma if p_g else 0
                    p_delta = p_g.delta if p_g else 0
                    p_iv = p_g.volatility if p_g else 0
                    p_oi = p_sum.open_interest if p_sum else 0
                    
                    if c_oi > 0 or p_oi > 0:
                        data_rows.append({
                            'Expiration Date': exp.expiration_date,
                            'Strike': strike.strike_price,
                            'Call Gamma': c_gamma,
                            'Call Delta': c_delta,
                            'Call IV': c_iv,
                            'Call OI': c_oi,
                            'Put Gamma': p_gamma,
                            'Put Delta': p_delta,
                            'Put IV': p_iv,
                            'Put OI': p_oi
                        })
                        
    except Exception as e:
        print(f"[ERROR] Streamer error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5. Output
    df = pd.DataFrame(data_rows)
    print(f"[RESULT] Collected {len(df)} rows. Spot: {current_spot}")
    
    if current_spot == 0 and len(df) > 0:
        # Pre-market or Closed market logic
        print("\n" + "!" * 50)
        print("[PROMPT] Live SPX quote not received (Market likely closed).")
        try:
            # Short timeout for input so it doesn't hang in auto-refresh (if used later)
            user_input = input("[INPUT] Enter current ES/SPX price to generate dashboard (or press Enter for 6900): ").strip()
            if user_input:
                current_spot = float(user_input)
            else:
                current_spot = 6900.0  # Safe default for current regime
        except:
            current_spot = 6900.0
        print(f"[ADJUST] Using manual spot: {current_spot}")
        print("!" * 50 + "\n")
        
    if not df.empty:
        # Convert to CBOE format (22 columns) for GammaEngine compatibility
        cboe_cols = [
            'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net', 'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
            'Strike',
            'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask', 'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
        ]
        
        # Add missing columns with 0
        for col in cboe_cols:
            if col not in df.columns:
                df[col] = 0
        
        # Reorder columns to match CBOE format
        df = df[cboe_cols]
        
        engine = GammaEngine()
        
        # Get current timestamp
        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        engine.load_dataframe(df, current_spot, date.today())
        output_file = "output/spx_live.html"
        engine.plot_full_dashboard(output_path=output_file, last_update_time=timestamp_str)
        print(f"[DONE] Dashboard generated: {output_file}")
        
        # Open in browser automatically
        abs_path = os.path.abspath(output_file)
        webbrowser.open(f"file:///{abs_path}")
        
        return True
    else:
        print("[FAIL] No data found.")
        return False

if __name__ == "__main__":
    try:
        asyncio.run(fetch_and_update_dashboard())
    except KeyboardInterrupt:
        print("\nStopped by user.")
