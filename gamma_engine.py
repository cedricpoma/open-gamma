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
    """
    Core engine for calculating Gamma Exposure and GEX Profile.

    FIX (2026-03-26): CBOE/Tastytrade-reported gammas are overestimated by ~68%
    on 0DTE strikes (likely a different normalization convention).
    All GEX calculations now use Black-Scholes recalculated gammas exclusively.
    The CBOE gamma columns are kept in options_df for reference but never used
    in any exposure calculation.
    """

    def __init__(self, contract_size=100):
        self.contract_size = contract_size
        self.spot_price = None
        self.data_date = None
        self.options_df = None

    # ------------------------------------------------------------------
    # DATA LOADING
    # ------------------------------------------------------------------

    def load_cboe_csv(self, file_path):
        """Loads data from CBOE quotedata CSV format."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'r') as f:
            lines = f.readlines()
            match_spot = re.search(r'Last: ([\d\.]+)', lines[1])
            spot_price = float(match_spot.group(1)) if match_spot else 0.0

            date_match = re.search(r'Date: (\w+ \w+ \d+ \d+)', lines[2])
            if date_match:
                try:
                    data_date = pd.to_datetime(date_match.group(1)).date()
                except Exception:
                    data_date = date.today()
            else:
                data_date = date.today()

        df = pd.read_csv(file_path, skiprows=3)
        cols = [
            'Expiration Date', 'Call Symbol', 'Call Last', 'Call Net',
            'Call Bid', 'Call Ask', 'Call Volume', 'Call IV', 'Call Delta',
            'Call Gamma', 'Call OI',
            'Strike',
            'Put Symbol', 'Put Last', 'Put Net', 'Put Bid', 'Put Ask',
            'Put Volume', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
        ]
        df.columns = cols
        self.load_dataframe(df, spot_price, data_date)

    def load_dataframe(self, df, spot_price, data_date):
        """
        Main data entry point. Standardizes the option chain and pre-computes
        BS gammas at spot price to replace unreliable broker-reported gammas.
        """
        self.spot_price = spot_price
        self.data_date = data_date

        numeric_cols = [
            'Call IV', 'Call Delta', 'Call Gamma', 'Call OI',
            'Strike', 'Put IV', 'Put Delta', 'Put Gamma', 'Put OI'
        ]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['Expiration Date'] = pd.to_datetime(df['Expiration Date'], errors='coerce')
        self.options_df = df.copy()

        # Pre-calculate Time to Expiry (T) in years
        # FIX (2026-03-31): Don't clip to 1 day anymore. 
        # T < 0 means expired. T = 0 means 0DTE.
        self.options_df['T'] = (
            self.options_df['Expiration Date'].dt.date - self.data_date
        ).apply(lambda x: x.days if pd.notnull(x) else -1) / 365.0

        # ------------------------------------------------------------------
        # FIX: Pre-compute BS gammas at spot and store as dedicated columns.
        # Use these everywhere instead of 'Call Gamma' / 'Put Gamma'.
        # ------------------------------------------------------------------
        self._precompute_bs_gammas_at_spot()

        total = len(self.options_df)
        active = ((self.options_df['Call OI'] > 0) | (self.options_df['Put OI'] > 0)).sum()
        print(
            f"[SUCCESS] Data Loaded: {total} strikes total, {active} active | {self.data_date}"
        )
        return self.options_df

    def _precompute_bs_gammas_at_spot(self):
        """
        Compute Black-Scholes gamma at the current spot price for every row.
        FIX (2026-03-31): Better 0DTE and Expired handling.
        """
        S = self.spot_price
        K = self.options_df['Strike'].values
        T = self.options_df['T'].values

        sigma_c = np.where(self.options_df['Call IV'].values <= 0, 1e-9,
                           self.options_df['Call IV'].values)
        sigma_p = np.where(self.options_df['Put IV'].values <= 0, 1e-9,
                           self.options_df['Put IV'].values)

        # Better T floor for 0DTE: 1/12th of a day (~2 hours) to avoid math infinity
        # but capture high gamma.
        # Options with T < 0 (yesterday or before) should have 0 gamma.
        T_floor = 1 / (365.0 * 12.0) 
        T_safe = np.where(T < 0, -1.0, np.maximum(T, T_floor))

        # Calculate d1 only for non-expired options
        active_mask = (T_safe > 0)
        d1_c = np.zeros_like(T_safe)
        d1_p = np.zeros_like(T_safe)
        
        # Avoid log(S/K) or sqrt(T) issues on inactive rows
        if active_mask.any():
            s_act = S
            k_act = K[active_mask]
            t_act = T_safe[active_mask]
            sig_c_act = sigma_c[active_mask]
            sig_p_act = sigma_p[active_mask]
            
            d1_c[active_mask] = (np.log(s_act / k_act) + 0.5 * sig_c_act**2 * t_act) / (sig_c_act * np.sqrt(t_act))
            d1_p[active_mask] = (np.log(s_act / k_act) + 0.5 * sig_p_act**2 * t_act) / (sig_p_act * np.sqrt(t_act))

        # Gamma calculation (0 for expired options)
        call_gamma = np.zeros_like(T_safe)
        put_gamma = np.zeros_like(T_safe)
        
        if active_mask.any():
            call_gamma[active_mask] = norm.pdf(d1_c[active_mask]) / (S * sigma_c[active_mask] * np.sqrt(T_safe[active_mask]))
            put_gamma[active_mask]  = norm.pdf(d1_p[active_mask]) / (S * sigma_p[active_mask] * np.sqrt(T_safe[active_mask]))

        self.options_df['Call Gamma BS'] = call_gamma
        self.options_df['Put Gamma BS']  = put_gamma

    # ------------------------------------------------------------------
    # SPOT GEX  (uses BS gammas)
    # ------------------------------------------------------------------

    def calculate_spot_gex(self):
        """
        Calculates GEX at the current spot price using BS-recalculated gammas.
        Previously used broker-reported 'Call Gamma' which was overestimated ~68%.
        """
        if self.options_df is None or self.spot_price is None:
            return 0

        S = self.spot_price
        cs = self.contract_size
        df = self.options_df

        call_gex = (df['Call Gamma BS'] * cs * df['Call OI'] * S**2 * 0.01).sum()
        put_gex  = (df['Put Gamma BS']  * cs * df['Put OI']  * S**2 * 0.01 * -1).sum()
        return call_gex + put_gex

    # ------------------------------------------------------------------
    # STRIKE BREAKDOWN  (uses BS gammas)
    # ------------------------------------------------------------------

    def get_strike_gex(self, view_range_pct=0.15, noise_threshold_pct=0.15):
        """
        Returns a DataFrame with Net/Call/Put GEX per strike near the spot,
        computed with BS gammas.

        Previously the dashboard used raw CBOE gammas for this chart, causing
        a ~28% overestimate of the GEX magnitudes.

        Parameters
        ----------
        view_range_pct       : keep strikes within ±N% of spot (default ±15%)
        noise_threshold_pct  : drop strikes whose |GEX| < N% of the max (default 15%)
        """
        if self.options_df is None:
            return pd.DataFrame()

        S = self.spot_price
        cs = self.contract_size
        df = self.options_df.copy()

        df['Total GEX'] = (
            df['Call Gamma BS'] * df['Call OI'] -
            df['Put Gamma BS']  * df['Put OI']
        ) * cs * S**2 * 0.01

        df['Call GEX'] =  df['Call Gamma BS'] * df['Call OI'] * cs * S**2 * 0.01
        df['Put GEX']  = -df['Put Gamma BS']  * df['Put OI']  * cs * S**2 * 0.01

        summary = df.groupby('Strike').agg(
            Total_GEX=('Total GEX', 'sum'),
            Call_GEX=('Call GEX', 'sum'),
            Put_GEX=('Put GEX', 'sum'),
            Call_OI=('Call OI', 'sum'),
            Put_OI=('Put OI', 'sum'),
        ).reset_index()

        # Filter near spot
        summary = summary[
            (summary['Strike'] >= S * (1 - view_range_pct)) &
            (summary['Strike'] <= S * (1 + view_range_pct))
        ]

        # Noise filter
        if not summary.empty:
            max_abs = summary['Total_GEX'].abs().max()
            summary = summary[summary['Total_GEX'].abs() >= max_abs * noise_threshold_pct]

        summary = summary.sort_values('Strike').reset_index(drop=True)
        summary['PC_Ratio'] = summary.apply(
            lambda r: r['Put_OI'] / r['Call_OI'] if r['Call_OI'] > 0 else 0, axis=1
        )
        return summary

    # ------------------------------------------------------------------
    # VECTORIZED BS GREEKS  (profile calculations — unchanged)
    # ------------------------------------------------------------------

    def _vectorized_bs_gamma(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))

    def _vectorized_bs_delta(self, S_levels, K, T, sigma, is_call=True, r=0.0, q=0.0):
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
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return -np.exp(-q * T) * norm.pdf(d1) * (d2 / sigma)

    def _vectorized_bs_speed(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return -(gamma / S) * (d1 / (sigma * np.sqrt(T)) + 1)

    def _vectorized_bs_charm(self, S_levels, K, T, sigma, r=0.0, q=0.0):
        K = np.array(K)[:, np.newaxis]
        T = np.array(T)[:, np.newaxis]
        sigma = np.array(sigma)[:, np.newaxis]
        S = S_levels[np.newaxis, :]
        sigma = np.where(sigma <= 0, 1e-9, sigma)
        T = np.where(T <= 0, 1e-9, T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return -np.exp(-q * T) * norm.pdf(d1) * (
            (r - q) / (sigma * np.sqrt(T)) - d2 / (2 * T)
        )

    # ------------------------------------------------------------------
    # PROFILE CALCULATIONS  (unchanged — already used BS)
    # ------------------------------------------------------------------

    def get_gamma_profile(self, price_range_pct=0.1, n_points=100):
        if self.options_df is None or self.spot_price is None:
            return None, None
        levels = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points
        )
        df = self.options_df
        c_g = self._vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Call IV'])
        p_g = self._vectorized_bs_gamma(levels, df['Strike'], df['T'], df['Put IV'])
        call_gex = (c_g * df['Call OI'].values[:, np.newaxis] * self.contract_size * levels**2 * 0.01).sum(axis=0)
        put_gex  = (p_g * df['Put OI'].values[:, np.newaxis]  * self.contract_size * levels**2 * 0.01 * -1).sum(axis=0)
        return levels, call_gex + put_gex

    def find_zero_gamma(self, levels, profile):
        for i in range(len(profile) - 1):
            if (profile[i] < 0 and profile[i+1] > 0) or (profile[i] > 0 and profile[i+1] < 0):
                return levels[i] - profile[i] * (levels[i+1] - levels[i]) / (profile[i+1] - profile[i])
        return None

    def find_vanna_flip(self, levels, profile):
        for i in range(len(profile) - 1):
            if (profile[i] < 0 and profile[i+1] > 0) or (profile[i] > 0 and profile[i+1] < 0):
                return float(levels[i] - profile[i] * (levels[i+1] - levels[i]) / (profile[i+1] - profile[i]))
        return None

    def get_charm_profile(self, price_range_pct=0.1, n_points=100):
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points
        )
        df = self.options_df
        c_charm = self._vectorized_bs_charm(levels, df['Strike'], df['T'], df['Call IV'])
        p_charm = self._vectorized_bs_charm(levels, df['Strike'], df['T'], df['Put IV'])
        call_exp = (c_charm * df['Call OI'].values[:, np.newaxis] * self.contract_size).sum(axis=0) / 365.0
        put_exp  = (p_charm * df['Put OI'].values[:, np.newaxis]  * self.contract_size * -1).sum(axis=0) / 365.0
        return {'levels': levels, 'net_charm': call_exp + put_exp, 'call_charm': call_exp, 'put_charm': put_exp}

    def get_vanna_profile(self, price_range_pct=0.1, n_points=100, max_dte=None):
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points
        )
        df = self.options_df
        if max_dte is not None:
            df = df[(df['T'] * 365.0) <= max_dte]
            if df.empty:
                return None
        c_v = self._vectorized_bs_vanna(levels, df['Strike'], df['T'], df['Call IV'])
        p_v = self._vectorized_bs_vanna(levels, df['Strike'], df['T'], df['Put IV'])
        tw = np.sqrt(df['T'].values * 365.0)[:, np.newaxis]
        c_v *= tw; p_v *= tw
        c_exp = (c_v * df['Call OI'].values[:, np.newaxis] * self.contract_size).sum(axis=0)
        p_exp = (p_v * df['Put OI'].values[:, np.newaxis]  * self.contract_size * -1).sum(axis=0)
        return {'levels': levels, 'net': c_exp + p_exp, 'call': c_exp, 'put': p_exp}

    def get_delta_profile(self, price_range_pct=0.1, n_points=100):
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points
        )
        df = self.options_df
        c_d = self._vectorized_bs_delta(levels, df['Strike'], df['T'], df['Call IV'], is_call=True)
        p_d = self._vectorized_bs_delta(levels, df['Strike'], df['T'], df['Put IV'], is_call=False)
        c_exp = (c_d * df['Call OI'].values[:, np.newaxis] * self.contract_size).sum(axis=0)
        p_exp = (p_d * df['Put OI'].values[:, np.newaxis]  * self.contract_size).sum(axis=0)
        return {'levels': levels, 'net': c_exp + p_exp, 'call': c_exp, 'put': p_exp}

    def get_speed_profile(self, price_range_pct=0.1, n_points=100):
        if self.options_df is None or self.spot_price is None:
            return None
        levels = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points
        )
        df = self.options_df
        c_sp = self._vectorized_bs_speed(levels, df['Strike'], df['T'], df['Call IV'])
        p_sp = self._vectorized_bs_speed(levels, df['Strike'], df['T'], df['Put IV'])
        c_exp = (c_sp * df['Call OI'].values[:, np.newaxis] * self.contract_size * levels**2 * 0.01).sum(axis=0)
        p_exp = (p_sp * df['Put OI'].values[:, np.newaxis]  * self.contract_size * levels**2 * 0.01 * -1).sum(axis=0)
        return {'levels': levels, 'net': c_exp + p_exp}

    def get_surface_data(self, price_range_pct=0.05, n_points_price=100, n_points_time=50):
        if self.options_df is None or self.spot_price is None:
            return None
        prices = np.linspace(
            self.spot_price * (1 - price_range_pct),
            self.spot_price * (1 + price_range_pct), n_points_price
        )
        times = np.linspace(0, 6.5, n_points_time) / (24 * 365)
        df = self.options_df
        gamma_surface = np.zeros((n_points_price, n_points_time))
        charm_surface = np.zeros((n_points_price, n_points_time))
        for i, t_snap in enumerate(times):
            T_snap = np.maximum(df['T'].values - t_snap, 1 / 365.0 / 24.0)
            c_g = self._vectorized_bs_gamma(prices, df['Strike'], T_snap, df['Call IV'])
            p_g = self._vectorized_bs_gamma(prices, df['Strike'], T_snap, df['Put IV'])
            gamma_surface[:, i] = (
                (c_g * df['Call OI'].values[:, np.newaxis] * self.contract_size * prices**2 * 0.01).sum(axis=0) +
                (p_g * df['Put OI'].values[:, np.newaxis]  * self.contract_size * prices**2 * 0.01 * -1).sum(axis=0)
            )
            charm_val = self._vectorized_bs_charm(prices, df['Strike'], T_snap, df['Call IV'])
            charm_surface[:, i] = (
                (df['Call OI'].values[:, np.newaxis] - df['Put OI'].values[:, np.newaxis]) *
                charm_val * self.contract_size
            ).sum(axis=0)
        return {
            'prices': prices,
            'times': np.linspace(0, 6.5, n_points_time),
            'gamma': gamma_surface,
            'charm': charm_surface
        }

    # ------------------------------------------------------------------
    # STATIC PLOT (matplotlib)
    # ------------------------------------------------------------------

    def plot_profile(self, levels, profile, zero_gamma, output_path='output/gamma_profile.png'):
        plt.figure(figsize=(12, 7))
        plt.plot(levels, profile / 1e9, label='Gamma Exposure (BS)', color='#1f77b4', linewidth=2.5)
        plt.axhline(0, color='black', linestyle='-', alpha=0.5, linewidth=1)
        plt.axvline(self.spot_price, color='red', linestyle='--',
                    label=f'Spot ({self.spot_price:.2f})')
        if zero_gamma:
            plt.axvline(zero_gamma, color='green', linestyle='--',
                        label=f'Zero Gamma ({zero_gamma:.2f})')
            plt.scatter([zero_gamma], [0], color='green', s=100, zorder=5, edgecolors='white')
        plt.scatter([self.spot_price], [self.calculate_spot_gex() / 1e9],
                    color='red', s=100, zorder=5, edgecolors='white')
        plt.title('SPX Gamma Exposure Profile (BS-corrected)', fontsize=16, fontweight='bold')
        plt.xlabel('Index Level', fontsize=13)
        plt.ylabel('Total Gamma Exposure ($B / 1%)', fontsize=13)
        plt.grid(True, alpha=0.2)
        plt.legend(frameon=True, shadow=True)
        plt.fill_between(levels, 0, profile / 1e9, where=(profile > 0), color='green', alpha=0.15)
        plt.fill_between(levels, 0, profile / 1e9, where=(profile < 0), color='red', alpha=0.15)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        return output_path

    # ------------------------------------------------------------------
    # FULL DASHBOARD (plotly)
    # ------------------------------------------------------------------

    def plot_full_dashboard(self, output_path='output/spx_dynamic_dashboard.html',
                            last_update_time=None):
        print("[INFO] Generating surfaces...")
        surface_data = self.get_surface_data(n_points_price=200, n_points_time=50)

        print("[INFO] Calculating profiles...")
        levels_gamma, total_gamma = self.get_gamma_profile(price_range_pct=0.1, n_points=500)
        zero_gamma_level = self.find_zero_gamma(levels_gamma, total_gamma)
        charm_profile = self.get_charm_profile(price_range_pct=0.1, n_points=500)

        # Strike breakdown — now uses BS gammas via get_strike_gex()
        strike_summary = self.get_strike_gex(view_range_pct=0.03, noise_threshold_pct=0.15)
        strike_summary = strike_summary.rename(columns={
            'Total_GEX': 'Total GEX', 'Call_GEX': 'Call GEX',
            'Put_GEX': 'Put GEX', 'Call_OI': 'Call OI', 'Put_OI': 'Put OI'
        })
        view_min = self.spot_price * 0.97
        view_max = self.spot_price * 1.03

        fig = make_subplots(
            rows=2, cols=3,
            subplot_titles=(
                '<b>GAMMA (Price x Time)</b>', '<b>NET GEX BY STRIKE (BS)</b>',
                '<b>CHARM (Price x Time)</b>',
                '<b>NET CHARM PROFILE (Daily)</b>', '<b>CALL vs PUT CHARM (Daily)</b>', ''
            ),
            column_widths=[0.33, 0.33, 0.33],
            vertical_spacing=0.15
        )

        # Gamma heatmap
        z_g = surface_data['gamma']
        z_max_g = np.percentile(np.abs(z_g), 99)
        fig.add_trace(go.Heatmap(
            z=z_g, x=surface_data['times'], y=surface_data['prices'],
            colorscale=[[0, '#E65100'], [0.45, '#FFF3E0'], [0.5, '#FFFFFF'],
                        [0.55, '#E3F2FD'], [1, '#0D47A1']],
            zmid=0, zmin=-z_max_g, zmax=z_max_g, showscale=False, zsmooth='best'
        ), row=1, col=1)
        fig.add_trace(go.Contour(
            z=z_g, x=surface_data['times'], y=surface_data['prices'],
            contours=dict(start=0, end=0, coloring='none', showlabels=False),
            line=dict(color='black', width=1, dash='dot'), showscale=False
        ), row=1, col=1)

        # Strike GEX bar (BS-corrected)
        colors = ['#1565C0' if g >= 0 else '#D32F2F' for g in strike_summary['Total GEX']]
        fig.add_trace(go.Bar(
            x=strike_summary['Total GEX'] / 1e6, y=strike_summary['Strike'],
            orientation='h', marker=dict(color=colors), name='Net GEX (BS)'
        ), row=1, col=2)

        # Charm heatmap
        z_c = surface_data['charm']
        z_max_c = np.percentile(np.abs(z_c), 99)
        fig.add_trace(go.Heatmap(
            z=z_c, x=surface_data['times'], y=surface_data['prices'],
            colorscale=[[0, '#FFB300'], [0.45, '#FFF8E1'], [0.5, '#FFFFFF'],
                        [0.55, '#E0F2F1'], [1, '#00ACC1']],
            zmid=0, zmin=-z_max_c, zmax=z_max_c, showscale=False, zsmooth='best'
        ), row=1, col=3)
        fig.add_trace(go.Contour(
            z=z_c, x=surface_data['times'], y=surface_data['prices'],
            contours=dict(start=0, end=0, coloring='none', showlabels=False),
            line=dict(color='black', width=1, dash='dot'), showscale=False
        ), row=1, col=3)

        # Charm profiles
        if charm_profile:
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['net_charm'],
                mode='lines', name='Net Charm', line=dict(color='#7B1FA2', width=2.5)
            ), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['net_charm'],
                mode='none', fill='tozeroy', fillcolor='rgba(123,31,162,0.1)', showlegend=False
            ), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['call_charm'],
                mode='lines', name='Call Charm', line=dict(color='#00C853', width=2)
            ), row=2, col=2)
            fig.add_trace(go.Scatter(
                x=charm_profile['levels'], y=charm_profile['put_charm'],
                mode='lines', name='Put Charm', line=dict(color='#D32F2F', width=2)
            ), row=2, col=2)
            fig.add_hline(y=0, row=2, col=1, line_width=1, line_color='black')
            fig.add_hline(y=0, row=2, col=2, line_width=1, line_color='black')
            fig.add_vline(x=self.spot_price, row=2, col=1,
                          line_dash='dash', line_color='#FF9800', annotation_text='SPOT')
            fig.add_vline(x=self.spot_price, row=2, col=2,
                          line_dash='dash', line_color='#FF9800', annotation_text='SPOT')

        ts = f" | Last Update: {last_update_time}" if last_update_time else ""
        fig.update_layout(
            template='plotly_white',
            title=dict(
                text=f'<b>SPX OPTIONALITY DEPTH & CHARM</b> | {self.data_date}{ts} | BS-corrected gammas',
                x=0.05
            ),
            height=900, showlegend=False,
            paper_bgcolor='#F8F9FA', plot_bgcolor='white',
            margin=dict(l=50, r=50, t=80, b=50),
        )
        for r in [1, 2]:
            for c in [1, 2, 3]:
                if r == 2 and c == 3:
                    continue
                fig.update_yaxes(showgrid=True, gridcolor='#F0F0F0', row=r, col=c)
                fig.update_xaxes(showgrid=True, gridcolor='#F0F0F0', row=r, col=c)

        fig.update_yaxes(range=[view_min, view_max], row=1, col=1)
        fig.update_yaxes(range=[view_min, view_max], row=1, col=2)
        fig.update_yaxes(range=[view_min, view_max], row=1, col=3)

        time_labels = ["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
        time_ticks  = [0, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
        for c in [1, 3]:
            fig.update_xaxes(tickvals=time_ticks, ticktext=time_labels,
                             range=[0, 6.5], row=1, col=c)

        fig.update_xaxes(range=[view_min, view_max], row=2, col=1, title="Spot Price")
        fig.update_xaxes(range=[view_min, view_max], row=2, col=2, title="Spot Price")

        for col in [1, 2, 3]:
            fig.add_hline(y=self.spot_price, line_dash='dash', line_color='#D32F2F',
                          opacity=0.8, row=1, col=col)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.write_html(output_path)
        return output_path

    def plot_interactive_dashboard(self, levels, profile, zero_gamma,
                                   output_path='output/spx_interactive.html'):
        return self.plot_full_dashboard(output_path)
