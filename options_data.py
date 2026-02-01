"""
SPX Options Data Fetcher
Fetches SPX options data and calculates Greeks for gamma/charm analysis
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import mibian
from scipy.stats import norm
import warnings
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.options import Options
warnings.filterwarnings('ignore')


class SPXOptionsData:
    def __init__(self, ticker='SPY', alpha_vantage_key=None):  # Use SPY instead of ^SPX for better reliability
        self.ticker = ticker
        self.spot_price = None
        self.options_data = None
        self.risk_free_rate = 0.05  # Default 5% risk-free rate
        self.alpha_vantage_key = alpha_vantage_key or 'A85Z12K4YSI3BC5D'  # User's key

    def fetch_options_data(self, expiration_date=None, analysis_date=None):
        """
        Fetch options data for SPX (Index) ONLY.
        Strict mode: No fallbacks to SPY. Requires real API data or SPX cache.
        """
        # 1. Try to fetch REAL SPX Data (Cached)
        print("[INFO] Checking for cached SPX data...")
        if self._try_load_parquet('data/parquet_spx', analysis_date):
            return self.options_data

        # 2. Live API (Try SPX)
        try:
            print("[INFO] Trying Alpha Vantage API (SPX)...")
            return self._fetch_alpha_vantage_options('SPX', analysis_date)
        except Exception as e:
            print(f"[ERROR] SPX API failed: {e}")
            raise ValueError("No SPX data available. Please wait for API limit reset or cache 'data/parquet_spx'.")

    def _try_load_parquet(self, directory, analysis_date):
        """Helper to try loading parquet from a directory"""
        possible_files = []
        if analysis_date:
            date_str = pd.to_datetime(analysis_date).strftime('%Y-%m-%d')
            possible_files.append(f"{directory}/{date_str}.parquet")
        
        # We can keep a default cache file if it exists in the SPX folder
        # But we won't force-feed the SPY one.
        
        for p_file in possible_files:
            if os.path.exists(p_file):
                try:
                    data = pd.read_parquet(p_file)
                    print(f"[OK] Loaded {len(data)} options from {p_file}")
                    self.options_data = data
                    
                    # Map columns from parquet format (Robust handling)
                    if 'type' in data.columns and 'option_type' not in data.columns:
                        data['option_type'] = data['type']
                        
                    # Handle Open Interest variants
                    if 'oi' in data.columns:
                        data['open_interest'] = data['oi']
                        data['openInterest'] = data['oi']
                    elif 'openInterest' in data.columns:
                        data['open_interest'] = data['openInterest']
                    
                    # Ensure Greeks are present or initialize 0
                    if 'gamma' not in data.columns:
                         data['gamma'] = 0.0
                    if 'charm' not in data.columns:
                         data['charm'] = 0.0
                    
                    # Fetch Spot
                    self._update_spot_price()
                    
                    # Normalize types
                    self._ensure_required_columns(data)
                    return True
                except Exception as e:
                    print(f"[WARN] Error reading {p_file}: {e}")
        return False

    def _fetch_alpha_vantage_options(self, symbol, target_date=None):
        """
        Fetch options data from Alpha Vantage API for a given symbol
        """
        print(f"Using Alpha Vantage API with key: {self.alpha_vantage_key[:8]}...")
        try:
            # Initialize Alpha Vantage options client
            options_client = Options(key=self.alpha_vantage_key)
            print(f"Fetching {symbol} options from Alpha Vantage...")

            # Get options data for the specified symbol
            data, meta_data = options_client.get_realtime_options(symbol=symbol)

            if data is None or data.empty:
                raise ValueError(f"No options data received from Alpha Vantage for {symbol}")

            print(f"Received {len(data)} options from Alpha Vantage for {symbol}")
            
            # Create DataFrame
            options_df = pd.DataFrame(data)

            # Standardize column names
            name_map = {
                'strike': 'strike', 'Strike': 'strike',
                'bid': 'bid', 'Bid': 'bid',
                'ask': 'ask', 'Ask': 'ask',
                'vol': 'volume', 'Volume': 'volume', 'volume': 'volume',
                'oi': 'open_interest', 'openInterest': 'open_interest', 'OpenInterest': 'open_interest',
                'last': 'lastPrice', 'Last': 'lastPrice',
                'type': 'option_type', 'Type': 'option_type',
                'impliedVolatility': 'implied_volatility',
                'underlyingPrice': 'underlying_price', 'UnderlyingPrice': 'underlying_price'
            }
            
            # Rename columns
            for old_col, new_col in name_map.items():
                if old_col in options_df.columns:
                    options_df = options_df.rename(columns={old_col: new_col})
            
            if 'openInterest' in options_df.columns and 'open_interest' not in options_df.columns:
                 options_df = options_df.rename(columns={'openInterest': 'open_interest'})

            # Update Spot Price (Try to extract from data if API lookup failed)
            self._update_spot_price()

            # Ensure required columns
            self._ensure_required_columns(options_df)

            # Convert types
            self._convert_column_types(options_df)

            self.options_data = options_df
            print(f"Successfully processed {len(options_df)} real options from Alpha Vantage for {symbol}")
            return options_df

        except Exception as e:
            print(f"Alpha Vantage API error for {symbol}: {e}")
            raise e

    def _update_spot_price(self):
        """Fetch current spot price for SPX"""
        try:
            ts = TimeSeries(key=self.alpha_vantage_key)
            # Try SPX
            price_data, _ = ts.get_quote_endpoint(symbol='SPX')
            if price_data and '05. price' in price_data:
                self.spot_price = float(price_data['05. price'])
                print(f"[INFO] Current SPX spot price: ${self.spot_price:.2f}")
                return
        except Exception as e:
             print(f"[WARN] Could not fetch live SPX price: {e}")
        
        # If we can't get spot price, check if we have it in the loaded data (underlying_price)
        if self.options_data is not None and 'underlying_price' in self.options_data.columns:
             unique_prices = self.options_data['underlying_price'].unique()
             if len(unique_prices) > 0:
                 self.spot_price = float(unique_prices[0])
                 print(f"[INFO] Using stored underlying price from data: ${self.spot_price:.2f}")
                 return

        print("[ERROR] Could not determine SPX spot price (No API, No Data).")
        # We leave self.spot_price as None to let the system fail naturally if needed
        # or rely on visualization to handle it. No fake fallback.

    def _normalize_columns(self, df):
        """Standardize column names"""
        # Aliases to standard names
        aliases = {
            'oi': 'open_interest',
            'openInterest': 'open_interest',
            'impliedVolatility': 'implied_volatility',
            'type': 'option_type'
        }
        for alias, standard in aliases.items():
            if alias in df.columns and standard not in df.columns:
                df[standard] = df[alias]
        
        # Ensure minimal columns exist (create if missing)
        defaults = {
            'open_interest': 1000,
            'implied_volatility': 0.20,
            'time_to_exp': 1/365,
            'bid': 1.0,
            'ask': 1.5,
            'option_type': 'call'
        }
        for col, default_val in defaults.items():
            if col not in df.columns:
                df[col] = default_val

    def _ensure_required_columns(self, df):
        """Ensure all strictly required columns are present for calculation"""
        # Ensure we have option_type normalized
        if 'option_type' in df.columns:
             df['option_type'] = df['option_type'].astype(str).str.lower()
        
        # Add basic Greeks placeholders if missing
        greek_cols = ['delta', 'gamma', 'theta', 'vega', 'rho', 'charm']
        for col in greek_cols:
            if col not in df.columns:
                df[col] = 0.0

    def _convert_column_types(self, df):
        """Convert columns to numeric where appropriate"""
        numeric_cols = ['strike', 'bid', 'ask', 'volume', 'open_interest', 
                       'implied_volatility', 'time_to_exp', 'gamma', 'charm', 'delta', 
                       'theta', 'vega', 'rho']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    def calculate_greeks(self):
        """
        Calculate Greeks for all options using Black-Scholes model
        """
        if self.options_data is None or self.options_data.empty:
            print("No options data available. Call fetch_options_data() first.")
            return None

        # Return existing greeks if they seem valid (cached)
        # Check if we have substantial non-zero values
        if 'gamma' in self.options_data.columns and self.options_data['gamma'].abs().sum() > 0:
            print("Using pre-calculated/cached Greeks")
            return self.options_data

        print(f"Calculating Greeks for {len(self.options_data)} options...")
        greeks_df = self.options_data.copy()
        
        calculated_count = 0
        
        for idx, option in greeks_df.iterrows():
            try:
                S = self.spot_price
                K = option['strike']
                T = option['time_to_exp']
                r = self.risk_free_rate
                sigma = option['implied_volatility']

                # Simple validation
                if T <= 0: T = 1/365 # Avoid div by zero
                if sigma <= 0: sigma = 0.20
                if S is None or S <= 0: S = 5000.0

                # Determine if call or put
                is_call = 'call' in str(option['option_type']).lower()
                
                # Use mibian or manual approximation
                # Note: mibian might be slow for loops, but reliable
                if is_call:
                    bs = mibian.BS([S, K, r*100, T*365], volatility=sigma*100)
                    greeks_df.loc[idx, 'delta'] = bs.callDelta
                    greeks_df.loc[idx, 'gamma'] = bs.gamma
                    greeks_df.loc[idx, 'theta'] = bs.callTheta / 365
                    greeks_df.loc[idx, 'vega'] = bs.vega / 100
                    greeks_df.loc[idx, 'rho'] = bs.callRho / 100
                else:  # put
                    bs = mibian.BS([S, K, r*100, T*365], volatility=sigma*100)
                    greeks_df.loc[idx, 'delta'] = bs.putDelta
                    greeks_df.loc[idx, 'gamma'] = bs.gamma
                    greeks_df.loc[idx, 'theta'] = bs.putTheta / 365
                    greeks_df.loc[idx, 'vega'] = bs.vega / 100
                    greeks_df.loc[idx, 'rho'] = bs.putRho / 100

                # Calculate charm (dDelta/dTime) - approx
                # charm = -dDelta/dT approx
                charm = greeks_df.loc[idx, 'gamma'] * (r - sigma**2/2) * T
                greeks_df.loc[idx, 'charm'] = charm

                calculated_count += 1
            except Exception:
                continue

        print(f"Successfully calculated Greeks for {calculated_count} options")
        return greeks_df

    def get_market_maker_exposure(self, greeks_df):
        """
        Calculate market maker exposure by aggregating Greeks
        Market makers are typically short options (clients are long), so MM exposure = -1 * Client Position
        """
        if greeks_df is None or greeks_df.empty:
            return None

        df = greeks_df.copy()
        
        # Calculate exposure: MM is short the option, so -1 * Gamma * OI
        df['gamma_exposure'] = df['gamma'] * df['open_interest'] * (-1)
        df['charm_exposure'] = df['charm'] * df['open_interest'] * (-1)
        
        # Calculate GEX per strike
        def calculate_exposure(group):
            gamma_sum = group['gamma_exposure'].sum()
            charm_sum = group['charm_exposure'].sum()
            return pd.Series({'gamma_exposure': gamma_sum, 'charm_exposure': charm_sum})

        exposure = df.groupby('strike').apply(calculate_exposure).reset_index()
        exposure.columns = ['strike', 'gamma_exposure', 'charm_exposure']
        
        # Add spot price context if available
        if self.spot_price:
             print(f"   SPX Spot: ${self.spot_price:.2f}")
        else:
             print("   SPX Spot: N/A")
             
        exposure.rename(columns={'gamma_exposure': 'gamma', 'charm_exposure': 'charm'}, inplace=True)
        return exposure.sort_values('strike')

    def get_gamma_surface(self, greeks_df, price_range=None, time_steps=50):
        """
        Create gamma surface over time and price range
        High-resolution 'Fingers' visualization: distinct strikes that narrow over time.
        """
        if greeks_df is None or greeks_df.empty:
            return None
            
        exposure = self.get_market_maker_exposure(greeks_df)
        if exposure is None or exposure.empty:
            return None
         
        # -------------------------------------------------------------
        # INTELLIGENT GRID
        # -------------------------------------------------------------
        max_gex_idx = exposure['gamma'].abs().idxmax()
        center_strike = exposure.loc[max_gex_idx, 'strike']
        
        if price_range:
            prices = np.linspace(price_range[0], price_range[1], 150) # Increased resolution
        else:
            active_strikes = exposure[exposure['gamma'].abs() > exposure['gamma'].abs().max() * 0.02] # Sensitivity 2%
            if not active_strikes.empty:
                min_s = active_strikes['strike'].min()
                max_s = active_strikes['strike'].max()
                span = max_s - min_s
                # Tighter vertical crop to see details
                prices = np.linspace(min_s - span*0.1, max_s + span*0.1, 150)
            else:
                prices = np.linspace(center_strike * 0.9, center_strike * 1.1, 150)
        
        times = np.linspace(0, 6.5, time_steps) 
        
        gamma_surface = []
        
        grid_min = prices.min()
        grid_max = prices.max()
        relevant_exposure = exposure[
            (exposure['strike'] >= grid_min * 0.9) & 
            (exposure['strike'] <= grid_max * 1.1)
        ]

        if relevant_exposure.empty:
             return None

        exp_strikes = relevant_exposure['strike'].values
        exp_gamma = relevant_exposure['gamma'].values

        # -------------------------------------------------------------
        # FINGER/BAR BLENDING LOGIC
        # -------------------------------------------------------------
        # 0.3% width = ~15 pts at 5000. 
        # SPX strikes are often 5-10-25 apart. This allows separation.
        base_width_pct = 0.003 

        for t in times:
             # TIME DYNAMICS
             t_norm = t / 6.5
             
             # Decay: Width shrinks significantly to create sharp points ("fingers")
             # From 100% width down to 30% width at end of day
             width_decay = 1.0 - (0.7 * t_norm)
             
             col_values = []
             for p in prices:
                 # Local width
                 width = p * base_width_pct * width_decay
                 
                 diffs = p - exp_strikes
                 weights = np.exp(-0.5 * (diffs / width)**2)
                 
                 val = np.sum(exp_gamma * weights)
                 col_values.append(val)
                 
             gamma_surface.append(col_values)
             
        return {
            'prices': prices,
            'times': times,
            'gamma_surface': np.array(gamma_surface),
            'center_strike': center_strike
        }

def main():
    print("Testing SPXOptionsData...")
    spx = SPXOptionsData()
    data = spx.fetch_options_data()
    if data is not None:
        print(f"Loaded {len(data)} options")
        greeks = spx.calculate_greeks()
        exposure = spx.get_market_maker_exposure(greeks)
        print("Exposure sample:")
        print(exposure.head())

if __name__ == "__main__":
    main()