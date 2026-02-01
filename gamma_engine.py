import pandas as pd
import numpy as np
import os
import re
from datetime import datetime, date
from scipy.stats import norm
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

class GammaEngine:
    """Core engine for calculating Gamma Exposure and GEX Profile."""
    
    def __init__(self, contract_size=100):
        self.contract_size = contract_size
        self.spot_price = None
        self.data_date = None
        self.options_df = None
        
    def load_cboe_csv(self, file_path):
        """Loads data from CBOE quotedata CSV format."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(file_path, 'r') as f:
            lines = f.readlines()
            # Line 2: S&P 500 INDEX,Last: 6963.7402,Change:  -13.5298
            match_spot = re.search(r'Last: ([\d\.]+)', lines[1])
            spot_price = float(match_spot.group(1)) if match_spot else 0.0
            
            # Line 3: Date: Wed Jan 14 2026 or Date: 14 janvier 2026...
            date_match = re.search(r'Date: (\w+ \w+ \d+ \d+)', lines[2])
            if date_match:
                try:
                    data_date = pd.to_datetime(date_match.group(1)).date()
                except:
                    data_date = date.today()
            else:
                data_date = date.today()
            
        df = pd.read_csv(file_path, skiprows=3)
        # CBOE Column mapping
        cols = [
            'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net', 'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
            'Strike',
            'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask', 'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
        ]
        df.columns = cols
        self.load_dataframe(df, spot_price, data_date)

    def load_dataframe(self, df, spot_price, data_date):
        """
        Main data entry point. Standardizes the option chain from any source (CBOE CSV or Live API).
        """
        self.spot_price = spot_price
        self.data_date = data_date
        
        # Ensure numeric columns
        numeric_cols = ['Call IV', 'Call Delta', 'Call Gamma', 'Call OI', 'Strike', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        df['Expiration Date'] = pd.to_datetime(df['Expiration Date'], errors='coerce')
        
        # DISABLED: Don't filter by OI - pre-market data often lacks OI for OTM strikes
        # self.options_df = df[(df['Call OI'] > 0) | (df['Put OI'] > 0)].copy()
        self.options_df = df.copy()
        print(f"[SUCCESS] Data Loaded: {len(self.options_df)} strikes active for {self.data_date}")
        
        # Pre-calculate Time to Expiry (T)
        self.options_df['T'] = (self.options_df['Expiration Date'].dt.date - self.data_date).apply(lambda x: x.days) / 365.0
        self.options_df['T'] = self.options_df['T'].clip(lower=1/365.0)
        
        return self.options_df

    def calculate_spot_gex(self):
        """Calculates GEX at the current spot price."""
        if self.options_df is None or self.spot_price is None:
            return 0
            
        call_gex = (self.options_df['Call Gamma'] * self.contract_size * self.options_df['Call OI'] * (self.spot_price ** 2) * 0.01).sum()
        put_gex = (self.options_df['Put Gamma'] * self.contract_size * self.options_df['Put OI'] * (self.spot_price ** 2) * 0.01 * (-1)).sum()
        
        return call_gex + put_gex

    def _vectorized_bs_gamma(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        """Vectorized Black-Scholes Gamma calculation."""
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return gamma

    def _vectorized_bs_delta(self, S_levels, K, T, sigma, is_call=True, r=0.0, q=0.0):
        """Vectorized Black-Scholes Delta calculation."""
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        if is_call:
            return np.exp(-q * T) * norm.cdf(d1)
        else:
            return np.exp(-q * T) * (norm.cdf(d1) - 1)

    def _vectorized_bs_vanna(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        """Vectorized Black-Scholes Vanna (dDelta/dVol) calculation."""
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        vanna = -np.exp(-q * T) * norm.pdf(d1) * (d2 / sigma)
        return vanna

    def _vectorized_bs_speed(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        """Vectorized Black-Scholes Speed (dGamma/dSpot) calculation."""
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
        speed = - (gamma / S) * (d1 / (sigma * np.sqrt(T)) + 1)
        return speed

    def get_gamma_profile(self, price_range_pct=0.1, n_points=100):
        """Calculates GEX profile across a range of spot levels."""
        if self.options_df is None or self.spot_price is None:
            return None, None
            
        levels = np.linspace(self.spot_price * (1 - price_range_pct), 
                             self.spot_price * (1 + price_range_pct), n_points)
        
        df = self.options_df
        
        # Calls
        call_gammas = self._vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Call IV'])
        call_gex = (call_gammas * (df['Call OI'].values[:, np.newaxis]) * self.contract_size * (levels**2) * 0.01).sum(axis=0)
        
        # Puts
        put_gammas = self._vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Put IV'])
        put_gex = (put_gammas * (df['Put OI'].values[:, np.newaxis]) * self.contract_size * (levels**2) * 0.01 * (-1)).sum(axis=0)
        
        total_profile = call_gex + put_gex
        return levels, total_profile

    def find_zero_gamma(self, levels, profile):
        """Finds the price level where Gamma Exposure flips from positive to negative."""
        for i in range(len(profile)-1):
            if (profile[i] < 0 and profile[i+1] > 0) or (profile[i] > 0 and profile[i+1] < 0):
                # Linear interpolation
                return levels[i] - profile[i] * (levels[i+1] - levels[i]) / (profile[i+1] - profile[i])
        return None

    def plot_profile(self, levels, profile, zero_gamma, output_path='output/gamma_profile.png'):
        """Generates a professional Gamma Profile plot."""
        plt.figure(figsize=(12, 7))
        plt.plot(levels, profile / 1e9, label='Gamma Exposure', color='#1f77b4', linewidth=2.5)
        plt.axhline(0, color='black', linestyle='-', alpha=0.5, linewidth=1)
        plt.axvline(self.spot_price, color='red', linestyle='--', label=f'Spot Price ({self.spot_price:.2f})')
        
        if zero_gamma:
            plt.axvline(zero_gamma, color='green', linestyle='--', label=f'Zero Gamma ({zero_gamma:.2f})')
            plt.scatter([zero_gamma], [0], color='green', s=100, zorder=5, edgecolors='white')
            
        plt.scatter([self.spot_price], [self.calculate_spot_gex() / 1e9], color='red', s=100, zorder=5, edgecolors='white')
        
        plt.title('SPX Gamma Exposure Profile', fontsize=16, fontweight='bold')
        plt.xlabel('Index Level', fontsize=13)
        plt.ylabel('Total Gamma Exposure ($ Billions / 1%)', fontsize=13)
        plt.grid(True, alpha=0.2)
        plt.legend(frameon=True, shadow=True)
        
        plt.fill_between(levels, 0, profile / 1e9, where=(profile > 0), color='green', alpha=0.15)
        plt.fill_between(levels, 0, profile / 1e9, where=(profile < 0), color='red', alpha=0.15)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        return output_path

    def _vectorized_bs_charm(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        """Vectorized Black-Scholes Charm (Delta Decay) calculation."""
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        # Charm formula for Call
        charm = -np.exp(-q * T) * norm.pdf(d1) * ( (r - q) / (sigma * np.sqrt(T)) - d2 / (2 * T) )
        return charm

    def get_surface_data(self, price_range_pct=0.05, n_points_price=100, n_points_time=50):
        """Generates Gamma and Charm surfaces (Price x Time)."""
        if self.options_df is None or self.spot_price is None:
            return None
            
        prices = np.linspace(self.spot_price * (1 - price_range_pct), 
                             self.spot_price * (1 + price_range_pct), n_points_price)
        
        # Hours from 9:30 AM to 4:00 PM (6.5 hours)
        times = np.linspace(0, 6.5, n_points_time) / (24 * 365) # Convert to years
        
        df = self.options_df
        
        gamma_surface = np.zeros((n_points_price, n_points_time))
        charm_surface = np.zeros((n_points_price, n_points_time))
        
        for i, t_snapshot in enumerate(times):
            # Time remaining at this snapshot
            T_snap = np.maximum(df['T'].values[:, np.newaxis] - t_snapshot, 1/365.0/24.0)
            
            # Gamma contribution
            c_gamma = self._vectorized_bs_gamma(prices, df['Strike'], T_snap[:, 0], df['Call IV'])
            p_gamma = self._vectorized_bs_gamma(prices, df['Strike'], T_snap[:, 0], df['Put IV'])
            
            g_exp = (c_gamma * df['Call OI'].values[:, np.newaxis] * self.contract_size * (prices**2) * 0.01).sum(axis=0) + \
                    (p_gamma * df['Put OI'].values[:, np.newaxis] * self.contract_size * (prices**2) * 0.01 * (-1)).sum(axis=0)
            
            gamma_surface[:, i] = g_exp
            
            # Charm contribution
            # ∂Delta/∂t is the same for Call and Put (if q=0, r=0)
            charm_val = self._vectorized_bs_charm(prices, df['Strike'], T_snap[:, 0], df['Call IV'])
            
            # Dealer Exposure = (CallOI - PutOI) * Charm
            # (Car MM est Long Call / Short Put face au client qui hedge avec des Puts)
            ch_exp = ( (df['Call OI'].values[:, np.newaxis] - df['Put OI'].values[:, np.newaxis]) * 
                       charm_val * self.contract_size ).sum(axis=0)
            
            charm_surface[:, i] = ch_exp
            
        return {
            'prices': prices,
            'times': np.linspace(0, 6.5, n_points_time),
            'gamma': gamma_surface,
            'charm': charm_surface
        }

    def get_charm_profile(self, price_range_pct=0.1, n_points=100):
        """Calculates Charm Exposure profile (Net, Call, Put) across a range of spot levels."""
        if self.options_df is None or self.spot_price is None:
            return None
            
        levels = np.linspace(self.spot_price * (1 - price_range_pct), 
                             self.spot_price * (1 + price_range_pct), n_points)
        
        df = self.options_df
        
        # Charm calculation (Charm * OI * Contract Size)
        # We calculate "Exposure" as the daily decay impact on Delta.
        
        # Calls
        call_charm_vals = self._vectorized_bs_charm(levels, df['Strike'], df['T'], df['Call IV'])
        call_charm_exp = (call_charm_vals * (df['Call OI'].values[:, np.newaxis]) * self.contract_size).sum(axis=0)
        
        # Puts
        put_charm_vals = self._vectorized_bs_charm(levels, df['Strike'], df['T'], df['Put IV'])
        put_charm_exp = (put_charm_vals * (df['Put OI'].values[:, np.newaxis]) * self.contract_size * (-1)).sum(axis=0)

        # Scale to Daily decay by dividing annual Charm by 365
        call_charm_exp /= 365.0
        put_charm_exp /= 365.0
        
        net_charm_profile = call_charm_exp + put_charm_exp
        
        return {
            'levels': levels,
            'net_charm': net_charm_profile,
            'call_charm': call_charm_exp,
            'put_charm': put_charm_exp
        }

    def get_vanna_profile(self, price_range_pct=0.1, n_points=100):
        """Calculates Vanna Exposure profile (Net, Call, Put)."""
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(self.spot_price * (1 - price_range_pct), self.spot_price * (1 + price_range_pct), n_points)
        df = self.options_df
        
        c_vanna = self._vectorized_bs_vanna(levels, df['Strike'], df['T'], df['Call IV'])
        p_vanna = self._vectorized_bs_vanna(levels, df['Strike'], df['T'], df['Put IV'])
        
        # Vanna Exp = Dealer is Long Calls / Short Puts? Usually clients buy calls and puts.
        # Dealer Exposure = (Call GEX - Put GEX equivalent)
        # We use the same sign convention as GEX: (Call - Put)
        c_exp = (c_vanna * (df['Call OI'].values[:, np.newaxis]) * self.contract_size).sum(axis=0)
        p_exp = (p_vanna * (df['Put OI'].values[:, np.newaxis]) * self.contract_size * (-1)).sum(axis=0)
        
        return {'levels': levels, 'net': c_exp + p_exp, 'call': c_exp, 'put': p_exp}

    def get_delta_profile(self, price_range_pct=0.1, n_points=100):
        """Calculates Net Delta Exposure profile by strike."""
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(self.spot_price * (1 - price_range_pct), self.spot_price * (1 + price_range_pct), n_points)
        df = self.options_df
        
        c_delta = self._vectorized_bs_delta(levels, df['Strike'], df['T'], df['Call IV'], is_call=True)
        p_delta = self._vectorized_bs_delta(levels, df['Strike'], df['T'], df['Put IV'], is_call=False)
        
        c_exp = (c_delta * (df['Call OI'].values[:, np.newaxis]) * self.contract_size).sum(axis=0)
        p_exp = (p_delta * (df['Put OI'].values[:, np.newaxis]) * self.contract_size).sum(axis=0) # Put delta is already negative
        
        return {'levels': levels, 'net': c_exp + p_exp, 'call': c_exp, 'put': p_exp}

    def get_speed_profile(self, price_range_pct=0.1, n_points=100):
        """Calculates Speed Exposure profile (Gamma of Gamma)."""
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(self.spot_price * (1 - price_range_pct), self.spot_price * (1 + price_range_pct), n_points)
        df = self.options_df
        
        c_speed = self._vectorized_bs_speed(levels, df['Strike'], df['T'], df['Call IV'])
        p_speed = self._vectorized_bs_speed(levels, df['Strike'], df['T'], df['Put IV'])
        
        # Speed Scale: GEX is (Gamma * Spot^2 * 0.01). 
        # dGEX/dS = d(Gamma * S^2 * 0.01)/dS = 0.01 * (Speed * S^2 + 2 * S * Gamma)
        # However, usually "Gamma Speed Exposure" is just Speed * OI * ContractSize * S^3... or similar.
        # Let's use simpler version: Change in GEX per 1% move.
        c_exp = (c_speed * (df['Call OI'].values[:, np.newaxis]) * self.contract_size * (levels**2) * 0.01).sum(axis=0)
        p_exp = (p_speed * (df['Put OI'].values[:, np.newaxis]) * self.contract_size * (levels**2) * 0.01 * (-1)).sum(axis=0)
        
        return {'levels': levels, 'net': c_exp + p_exp}

    def plot_full_dashboard(self, output_path='output/spx_dynamic_dashboard.html', last_update_time=None):
        """Generates the full dynamic dashboard including Gamma and Charm profiles."""
        
        print("[INFO] Generating high-resolution surfaces...")
        surface_data = self.get_surface_data(n_points_price=200, n_points_time=50)
        
        print("[INFO] Calculating Profiles...")
        # Gamma Profile
        levels_gamma, total_gamma = self.get_gamma_profile(price_range_pct=0.1, n_points=500)
        zero_gamma_level = self.find_zero_gamma(levels_gamma, total_gamma)
        
        # Charm Profile (New)
        charm_profile = self.get_charm_profile(price_range_pct=0.1, n_points=500)

        # 1. Prepare Strike Data (Existing GEX Bar chart)
        df = self.options_df.copy()
        df['Total GEX'] = (df['Call Gamma'] * df['Call OI'] - df['Put Gamma'] * df['Put OI']) * self.contract_size * (self.spot_price**2) * 0.01
        strike_summary = df.groupby('Strike')['Total GEX'].sum().reset_index()
        view_min, view_max = self.spot_price * 0.97, self.spot_price * 1.03
        strike_summary = strike_summary[
            (strike_summary['Strike'] >= view_min) & 
            (strike_summary['Strike'] <= view_max)
        ]

        # 2. Setup Figure - 2 Row Grid
        fig = make_subplots(
            rows=2, cols=3,
            subplot_titles=(
                '<b>GAMMA (Price x Time)</b>', '<b>NET GEX BY STRIKE</b>', '<b>CHARM (Price x Time)</b>',
                '<b>NET CHARM PROFILE (Daily)</b>', '<b>CALL vs PUT CHARM (Daily)</b>', ''
            ),
            column_widths=[0.33, 0.33, 0.33],
            vertical_spacing=0.15
        )

        # --- Row 1: Existing Plots ---
        
        # 1.1 Gamma Heatmap
        z_gamma = surface_data['gamma']
        z_max_g = np.percentile(np.abs(z_gamma), 99)
        gamma_colorscale = [
            [0.0, '#E65100'], [0.45, '#FFF3E0'], [0.5, '#FFFFFF'], [0.55, '#E3F2FD'], [1.0, '#0D47A1']
        ]
        fig.add_trace(go.Heatmap(
            z=z_gamma, x=surface_data['times'], y=surface_data['prices'],
            colorscale=gamma_colorscale, zmid=0, zmin=-z_max_g, zmax=z_max_g,
            showscale=False, zsmooth='best'
        ), row=1, col=1)
        
        # Zero Gamma Contour on Heatmap
        fig.add_trace(go.Contour(
            z=z_gamma, x=surface_data['times'], y=surface_data['prices'],
            contours=dict(start=0, end=0, coloring='none', showlabels=False),
            line=dict(color='black', width=1, dash='dot'), showscale=False
        ), row=1, col=1)

        # 1.2 Strike GEX Bar
        colors = ['#1565C0' if g >= 0 else '#D32F2F' for g in strike_summary['Total GEX']]
        fig.add_trace(go.Bar(
            x=strike_summary['Total GEX'] / 1e6, y=strike_summary['Strike'],
            orientation='h', marker=dict(color=colors), name='Net GEX'
        ), row=1, col=2)
        
        # 1.3 Charm Heatmap
        z_charm = surface_data['charm']
        z_max_c = np.percentile(np.abs(z_charm), 99)
        charm_colorscale = [
            [0.0, '#FFB300'], [0.45, '#FFF8E1'], [0.5, '#FFFFFF'], [0.55, '#E0F2F1'], [1.0, '#00ACC1']
        ]
        fig.add_trace(go.Heatmap(
            z=z_charm, x=surface_data['times'], y=surface_data['prices'],
            colorscale=charm_colorscale, zmid=0, zmin=-z_max_c, zmax=z_max_c,
            showscale=False, zsmooth='best'
        ), row=1, col=3)
        
        # Zero Charm Contour on Heatmap
        fig.add_trace(go.Contour(
            z=z_charm, x=surface_data['times'], y=surface_data['prices'],
            contours=dict(start=0, end=0, coloring='none', showlabels=False),
            line=dict(color='black', width=1, dash='dot'), showscale=False
        ), row=1, col=3)

        # --- Row 2: New Charm Plots ---
        
        # 2.1 Net Charm Profile (Purple Line)
        if charm_profile:
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['net_charm'],
                mode='lines', name='Net Charm', line=dict(color='#7B1FA2', width=2.5) # Purple
            ), row=2, col=1)
            
            # Fill Area
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['net_charm'],
                mode='none', fill='tozeroy', fillcolor='rgba(123, 31, 162, 0.1)', showlegend=False
            ), row=2, col=1)
            
            # 2.2 Call vs Put Charm
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['call_charm'],
                mode='lines', name='Call Charm', line=dict(color='#00C853', width=2) # Green
            ), row=2, col=2)
            
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['put_charm'],
                mode='lines', name='Put Charm', line=dict(color='#D32F2F', width=2) # Red
            ), row=2, col=2)
            
            # Add Zero Lines
            fig.add_hline(y=0, row=2, col=1, line_width=1, line_color='black')
            fig.add_hline(y=0, row=2, col=2, line_width=1, line_color='black')
            
            # Add Vertical Spot Line
            fig.add_vline(x=self.spot_price, row=2, col=1, line_dash="dash", line_color="#FF9800", annotation_text="SPOT")
            fig.add_vline(x=self.spot_price, row=2, col=2, line_dash="dash", line_color="#FF9800", annotation_text="SPOT")

        # Global Layout
        timestamp_str = f" | Last Update: {last_update_time}" if last_update_time else ""
        fig.update_layout(
            template='plotly_white',
            title=dict(text=f'<b>SPX OPTIONALITY DEPTH & CHARM</b> | {self.data_date}{timestamp_str}', x=0.05),
            height=900,
            showlegend=False,
            paper_bgcolor='#F8F9FA',
            plot_bgcolor='white',
            margin=dict(l=50, r=50, t=80, b=50),
        )
        
        # Axis Ranges
        for r in [1, 2]:
            for c in [1, 2, 3]:
                if r==2 and c==3: continue # Empty plot
                fig.update_yaxes(showgrid=True, gridcolor='#F0F0F0', row=r, col=c)
                fig.update_xaxes(showgrid=True, gridcolor='#F0F0F0', row=r, col=c)

        # Row 1 Axis (Y is Price for Heatmaps, X is GEX for Bar)
        fig.update_yaxes(range=[view_min, view_max], row=1, col=1)
        fig.update_yaxes(range=[view_min, view_max], row=1, col=3)
        fig.update_yaxes(range=[view_min, view_max], row=1, col=2) 

        # Time Axis for Heatmaps
        time_labels = ["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
        time_ticks = [0, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
        for c in [1, 3]:
             fig.update_xaxes(
                tickvals=time_ticks, ticktext=time_labels,
                range=[0, 6.5], row=1, col=c
            )
        
        # Row 2 Axis (X is Price)
        fig.update_xaxes(range=[view_min, view_max], row=2, col=1, title="Spot Price")
        fig.update_xaxes(range=[view_min, view_max], row=2, col=2, title="Spot Price")
        
        # Add Horizontal Spot Line to Row 1 Heatmaps
        for col in [1, 2, 3]:
             fig.add_hline(
                y=self.spot_price, line_dash="dash", line_color="#D32F2F", 
                opacity=0.8, row=1, col=col
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.write_html(output_path)
        return output_path

    # Keep previous methods for compatibility or remove if not needed
    def plot_interactive_dashboard(self, levels, profile, zero_gamma, output_path='output/spx_interactive.html'):
        return self.plot_full_dashboard(output_path)
