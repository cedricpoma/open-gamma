import os
import webbrowser
import asyncio
import pandas as pd
from datetime import date, datetime
from dotenv import load_dotenv

import logging

# Configure Logging for production (INFO level to see progress)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('tastytrade')
logger.setLevel(logging.INFO)

from gamma_engine import GammaEngine
from live_fetch import create_session, fetch_options_data, to_cboe_format, estimate_spot_fallback, TARGET_SYMBOL

load_dotenv()

async def fetch_and_update_dashboard():
    """Single iteration: fetch live data and update dashboard using shared module."""
    # 1. Authenticate via OAuth2
    session = create_session()
    if not session:
        print("[ERROR] Authentication failed. Check OAuth2 credentials in .env")
        return False

    # 2. Fetch live data via shared module
    try:
        df, current_spot = await fetch_options_data(session)
    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. Handle missing spot
    if current_spot == 0 and len(df) > 0:
        print("\n" + "!" * 50)
        print("[PROMPT] Live SPX quote not received (Market likely closed).")
        default_spot = estimate_spot_fallback(df)
        try:
            user_input = input(f"[INPUT] Enter current ES/SPX price (or Enter for {default_spot:.0f}): ").strip()
            if user_input:
                current_spot = float(user_input)
            else:
                current_spot = default_spot
        except (ValueError, EOFError):
            current_spot = default_spot
        print(f"[ADJUST] Using spot: {current_spot}")
        print("!" * 50 + "\n")
        
    # 4. Generate dashboard
    if not df.empty:
        df_cboe = to_cboe_format(df.copy())

        engine = GammaEngine()
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        engine.load_dataframe(df_cboe, current_spot, date.today())
        output_file = "output/spx_live.html"
        engine.plot_full_dashboard(output_path=output_file, last_update_time=timestamp_str)
        print(f"[DONE] Dashboard generated: {output_file}")

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
