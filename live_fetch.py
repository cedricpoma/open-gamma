"""
live_fetch.py — Module partagé pour le fetch live Tastytrade.

Ce module factorise la logique commune entre app.py et main_live.py :
  - Authentification OAuth2
  - Fetch de la chaîne d'options
  - Streaming DXLink (Quote, Greeks, Summary)
  - Construction du DataFrame résultant

Usage:
    from live_fetch import create_session, fetch_options_data, to_cboe_format
"""

import os
import asyncio
import pandas as pd
from datetime import date
from dotenv import load_dotenv

from tastytrade import Session, DXLinkStreamer
from tastytrade.instruments import NestedOptionChain
from tastytrade.dxfeed import Quote, Greeks, Summary

load_dotenv()

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

TARGET_SYMBOL = os.getenv("TARGET_SYMBOL", "SPX")
POLL_DURATION = 25.0  # seconds to poll for streaming data


# ═══════════════════════════════════════════════════════════════
# AUTHENTIFICATION
# ═══════════════════════════════════════════════════════════════

def create_session() -> Session | None:
    """
    Creates a Session using OAuth2 (provider_secret + refresh_token).
    Tastytrade has migrated to OAuth2 - username/password login is no longer supported.

    To set up OAuth2:
    1. Go to https://my.tastytrade.com → Manage → My Profile → API
    2. Create an OAuth application → get your client_secret
    3. Create a "grant" → get your refresh_token
    4. Add to .env: TASTY_PROVIDER_SECRET=<client_secret>
                    TASTY_REFRESH_TOKEN=<refresh_token>
    """
    provider_secret = os.getenv("TASTY_PROVIDER_SECRET", "")
    refresh_token = os.getenv("TASTY_REFRESH_TOKEN", "")

    if not provider_secret or not refresh_token:
        print("[ERROR] ============================================")
        print("[ERROR] OAuth2 credentials missing!")
        print("[ERROR] Tastytrade now requires OAuth2 authentication.")
        print("[ERROR] Username/password login is no longer supported.")
        print("[ERROR]")
        print("[ERROR] To fix this:")
        print("[ERROR] 1. Go to https://my.tastytrade.com")
        print("[ERROR] 2. Navigate to: Manage -> My Profile -> API")
        print("[ERROR] 3. Create an OAuth application -> copy client_secret")
        print("[ERROR] 4. Create a 'grant' -> copy refresh_token")
        print("[ERROR] 5. Add to your .env file:")
        print("[ERROR]    TASTY_PROVIDER_SECRET=your_client_secret")
        print("[ERROR]    TASTY_REFRESH_TOKEN=your_refresh_token")
        print("[ERROR] ============================================")
        return None

    print("[AUTH] Connecting via OAuth2...")
    try:
        session = Session(
            provider_secret=provider_secret,
            refresh_token=refresh_token,
            is_test=False
        )
        print(f"[AUTH] OAuth2 session created successfully!")
        return session
    except Exception as e:
        print(f"[CRITICAL] OAuth2 session creation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════
# FETCH OPTIONS DATA
# ═══════════════════════════════════════════════════════════════

async def fetch_options_data(
    session: Session,
    symbol: str = None,
    max_dte: int = 60,
    poll_duration: float = None,
    include_zero_oi: bool = False,
) -> tuple[pd.DataFrame, float]:
    """
    Fetches live options data from Tastytrade via DXLink streaming.

    Args:
        session: Authenticated Tastytrade Session.
        symbol: Target symbol (default: TARGET_SYMBOL from .env).
        max_dte: Maximum days to expiration to include (default: 60).
        poll_duration: How long to poll for data in seconds (default: POLL_DURATION).
        include_zero_oi: If True, include strikes with zero open interest.

    Returns:
        (DataFrame with options data, spot price as float)
    """
    if symbol is None:
        symbol = TARGET_SYMBOL
    if poll_duration is None:
        poll_duration = POLL_DURATION

    # 1. Fetch Chain
    print(f"[INFO] Fetching Chain for {symbol}...")
    chains = NestedOptionChain.get(session, symbol)
    if not chains:
        raise Exception(f"No chains found for {symbol}")
    chain = chains[0]
    print(f"[INFO] Chain received. Expirations: {len(chain.expirations)}")

    # 2. Filter Symbols by DTE
    streamer_symbols = []
    target_expirations = [
        e for e in chain.expirations
        if 0 <= (e.expiration_date - date.today()).days < max_dte
    ]
    print(f"[INFO] Processing {len(target_expirations)} expirations...")

    # Debug chain content
    all_strikes = []
    for exp in target_expirations:
        for s in exp.strikes:
            all_strikes.append(float(s.strike_price))

    if all_strikes:
        print(f"[CHAIN] {len(all_strikes)} strikes. Range: {min(all_strikes)} - {max(all_strikes)}")
    else:
        print("[CHAIN] No strikes found!")

    for exp in target_expirations:
        for strike in exp.strikes:
            streamer_symbols.append(strike.call_streamer_symbol)
            streamer_symbols.append(strike.put_streamer_symbol)

    # Spot symbol
    spot_symbol = symbol

    print(f"[INFO] Subscribing to {len(streamer_symbols)} option symbols...")

    # 3. Stream Data
    cache = {'quotes': {}, 'greeks': {}, 'summaries': {}}

    async with DXLinkStreamer(session) as streamer:
        print("[STREAM] Connected to DXLink.")
        await streamer.subscribe(Quote, [spot_symbol])
        await streamer.subscribe(Greeks, streamer_symbols)
        await streamer.subscribe(Summary, streamer_symbols)

        print(f"[STREAM] Polling for data ({poll_duration}s)...")
        start = asyncio.get_running_loop().time()
        poll_count = 0

        while (asyncio.get_running_loop().time() - start) < poll_duration:
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

            await asyncio.sleep(0.01)

        print(f"[INFO] Polling complete. Events: {poll_count}")

    # 4. Extract Spot
    current_spot = 0.0
    if spot_symbol in cache['quotes']:
        q = cache['quotes'][spot_symbol]
        bid = float(q.bid_price) if q.bid_price else 0.0
        ask = float(q.ask_price) if q.ask_price else 0.0
        current_spot = bid if (bid > 0) else ask
        print(f"[DATA] Spot: {current_spot}")
    else:
        print(f"[WARN] Spot symbol {spot_symbol} not found in quotes.")

    print(f"[DEBUG] Cache - Quotes: {len(cache['quotes'])}, Greeks: {len(cache['greeks'])}, Summaries: {len(cache['summaries'])}")

    # 5. Build DataFrame
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

            if include_zero_oi or c_oi > 0 or p_oi > 0:
                data_rows.append({
                    'Expiration Date': exp.expiration_date,
                    'Strike': strike.strike_price,
                    'Call Gamma': c_gamma, 'Call Delta': c_delta,
                    'Call IV': c_iv, 'Call OI': c_oi,
                    'Put Gamma': p_gamma, 'Put Delta': p_delta,
                    'Put IV': p_iv, 'Put OI': p_oi
                })

    print(f"[DEBUG] Built DataFrame with {len(data_rows)} rows")
    return pd.DataFrame(data_rows), current_spot


# ═══════════════════════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════════════════════

# CBOE-compatible column order
CBOE_COLUMNS = [
    'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net',
    'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta',
    'Call Gamma', 'Call OI',
    'Strike',
    'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask',
    'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
]


def to_cboe_format(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts a raw options DataFrame to CBOE-compatible format.
    Adds missing columns with default values and reorders.
    """
    for col in CBOE_COLUMNS:
        if col not in df.columns:
            df[col] = 0
    return df[CBOE_COLUMNS]


def estimate_spot_fallback(df: pd.DataFrame) -> float:
    """
    Estimates a spot price from strike data when live quote is unavailable.
    Returns median strike or a conservative default.
    """
    if df is not None and not df.empty and 'Strike' in df.columns:
        strike_vals = df['Strike'].dropna()
        if not strike_vals.empty:
            estimated = float(strike_vals.median())
            print(f"[WARN] Spot estimated from median strike: {estimated}")
            return estimated
    default = 5900.0
    print(f"[WARN] No strike data — using conservative default: {default}")
    return default
