#!/usr/bin/env python3
"""
Démonstration rapide de l'analyse Gamma/Charm SPX
Lance l'analyse complète avec sauvegarde automatique
"""

import os
import sys
from datetime import datetime

def main():
    print("🚀 Démarrage de l'analyse Gamma/Charm SPX...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Créer le dossier results s'il n'existe pas
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    print(f"🔄 Exécution de l'analyse avec sauvegarde dans {results_dir}...")
    print()

    # Importer et exécuter directement
    sys.path.append('.')

    try:
        from main import main as run_analysis
        # Simuler les arguments de ligne de commande
        original_argv = sys.argv
        sys.argv = ['main.py', '--save-dashboard', '--output-dir', results_dir, '--date', '2026-01-09']

        exit_code = run_analysis()

        # Restaurer argv
        sys.argv = original_argv

        if exit_code == 0:
            print()
            print("✅ Analyse terminée avec succès!")
            print(f"📊 Dashboard sauvegardé dans: {results_dir}/")

            # Lister les fichiers générés
            if os.path.exists(results_dir):
                files = [f for f in os.listdir(results_dir) if f.startswith('spx_analysis_')]
                if files:
                    print("📁 Fichiers générés:")
                    for file in sorted(files, reverse=True)[:3]:  # Afficher les 3 plus récents
                        print(f"   • {file}")

        return exit_code

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())


def create_demo_data():
    """Create realistic demo data for SPX options"""
    print("🎭 Creating demo data...")

    # Simulate SPX at 4500
    spot_price = 4500

    # Create realistic strike prices around spot
    strikes = np.arange(4200, 4800, 25)  # Strikes from 4200 to 4800

    # Simulate realistic option data
    options_data = []

    for strike in strikes:
        moneyness = strike / spot_price

        # Simulate call options
        call_price = max(spot_price - strike, 0) + 50 * np.exp(-0.5 * (np.log(moneyness))**2)
        call_iv = 0.18 + 0.05 * abs(np.log(moneyness))  # Higher IV for OTM options
        call_oi = np.random.poisson(5000 * np.exp(-0.5 * (np.log(moneyness))**2))

        # Simulate put options
        put_price = max(strike - spot_price, 0) + 50 * np.exp(-0.5 * (np.log(moneyness))**2)
        put_iv = call_iv
        put_oi = np.random.poisson(5000 * np.exp(-0.5 * (np.log(moneyness))**2))

        # Add calls
        options_data.append({
            'strike': strike,
            'option_type': 'call',
            'bid': call_price * 0.95,
            'ask': call_price * 1.05,
            'openInterest': call_oi,
            'volume': call_oi * 0.1,
            'impliedVolatility': call_iv
        })

        # Add puts
        options_data.append({
            'strike': strike,
            'option_type': 'put',
            'bid': put_price * 0.95,
            'ask': put_price * 1.05,
            'openInterest': put_oi,
            'volume': put_oi * 0.1,
            'impliedVolatility': put_iv
        })

    # Create DataFrame
    df = pd.DataFrame(options_data)

    # Add time to expiration (simulate weekly options)
    df['time_to_exp'] = 5 / 365  # 5 days to expiration

    print(f"✅ Created demo data: {len(df)} options")
    return df, spot_price


def demo_analysis():
    """Run complete demo analysis"""
    print("=" * 60)
    print("SPX Options Gamma/Charm Analysis Tool - DEMO")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Create demo data
    options_df, spot_price = create_demo_data()

    # Create a mock SPX data object
    class MockSPXData:
        def __init__(self, options_df, spot_price):
            self.options_data = options_df
            self.spot_price = spot_price
            self.risk_free_rate = 0.05

        def calculate_greeks(self):
            """Calculate Greeks for demo data"""
            print("🧮 Calculating Greeks for demo data...")

            greeks_data = []

            for idx, option in self.options_data.iterrows():
                try:
                    S = self.spot_price
                    K = option['strike']
                    T = option['time_to_exp']
                    r = self.risk_free_rate
                    sigma = option['impliedVolatility']

                    # Simple approximation for demo (normally would use Black-Scholes)
                    moneyness = K / S

                    # Approximate delta
                    if option['option_type'] == 'call':
                        delta = min(max((S - K) / (S * sigma * np.sqrt(T)) + 0.5, 0), 1)
                    else:
                        delta = min(max((K - S) / (S * sigma * np.sqrt(T)) - 0.5, -1), 0)

                    # Approximate gamma
                    gamma = np.exp(-0.5 * (np.log(moneyness)/sigma)**2) / (S * sigma * np.sqrt(T))

                    # Approximate other Greeks
                    theta = -S * sigma * gamma / (2 * np.sqrt(T))
                    vega = S * np.sqrt(T) * gamma
                    rho = T * delta

                    # Approximate charm (dDelta/dTime)
                    charm = gamma * (r - sigma**2/2) * T

                    greeks_data.append({
                        'strike': K,
                        'option_type': option['option_type'],
                        'delta': delta,
                        'gamma': gamma,
                        'theta': theta,
                        'vega': vega,
                        'rho': rho,
                        'charm': charm,
                        'open_interest': option.get('openInterest', 0),
                        'volume': option.get('volume', 0),
                        'bid': option.get('bid', 0),
                        'ask': option.get('ask', 0),
                        'implied_volatility': sigma,
                        'time_to_exp': T
                    })

                except Exception as e:
                    print(f"Error calculating Greeks for strike {option['strike']}: {e}")
                    continue

            greeks_df = pd.DataFrame(greeks_data)
            print(f"✅ Calculated Greeks for {len(greeks_df)} options")
            return greeks_df

        def get_market_maker_exposure(self, greeks_df):
            """Calculate MM exposure"""
            if greeks_df is None or greeks_df.empty:
                return None

            exposure = greeks_df.groupby('strike').agg({
                'gamma': lambda x: -x.sum() * 1000,
                'delta': lambda x: -x.sum() * 1000,
                'charm': lambda x: -x.sum() * 1000,
                'open_interest': 'sum'
            }).reset_index()

            exposure = exposure.sort_values('strike')
            return exposure

        def get_gamma_surface(self, greeks_df, price_range=None, time_steps=24):
            """Create gamma surface for demo"""
            if greeks_df is None or greeks_df.empty:
                return None

            if price_range is None:
                price_min = self.spot_price * 0.95
                price_max = self.spot_price * 1.05
                prices = np.linspace(price_min, price_max, 50)
            else:
                prices = np.linspace(price_range[0], price_range[1], 50)

            times = np.linspace(0, 6.5/24, time_steps)

            gamma_surface = []

            for t in times:
                remaining_time = greeks_df['time_to_exp'].iloc[0] - t
                if remaining_time <= 0:
                    continue

                gamma_at_time = []

                for price in prices:
                    total_gamma = 0

                    for idx, option in greeks_df.iterrows():
                        try:
                            S = price
                            K = option['strike']
                            moneyness = K / S
                            sigma = option['implied_volatility']

                            gamma = np.exp(-0.5 * (np.log(moneyness)/sigma)**2) / (S * sigma * np.sqrt(remaining_time))
                            oi = option.get('open_interest', 1)
                            total_gamma += gamma * oi * (-1)

                        except:
                            continue

                    gamma_at_time.append(total_gamma)

                gamma_surface.append(gamma_at_time)

            return {
                'prices': prices,
                'times': times,
                'gamma_surface': np.array(gamma_surface)
            }

    # Create mock data object
    spx_data = MockSPXData(options_df, spot_price)

    # Calculate Greeks
    greeks_df = spx_data.calculate_greeks()

    if greeks_df is None:
        print("❌ Failed to calculate Greeks")
        return

    # Calculate exposure
    exposure_df = spx_data.get_market_maker_exposure(greeks_df)

    if exposure_df is not None:
        print("✅ Market maker exposure calculated")
        print(f"   Strikes analyzed: {len(exposure_df)}")
        print(f"   SPX Spot: ${spx_data.spot_price:.2f}")
        print()

    # Create visualizer
    print("🎨 Creating visualizations...")
    viz = OptionsVisualizer(spx_data)

    # Create combined dashboard
    print("📊 Creating combined dashboard...")
    fig = viz.create_combined_dashboard()
    plt.show()

    print()
    print("🎯 Analysis Summary:")
    print("-" * 30)

    if exposure_df is not None and not exposure_df.empty:
        max_gamma_idx = exposure_df['gamma'].abs().idxmax()
        max_gamma_strike = exposure_df.loc[max_gamma_idx, 'strike']
        max_gamma_value = exposure_df.loc[max_gamma_idx, 'gamma']

        print(f"   Strike with max gamma exposure: ${max_gamma_strike:.0f} (γ = {max_gamma_value:.2f})")
        if max_gamma_value > 0:
            print("   → Régime: Mean Reversion (range/scalping)")
        else:
            print("   → Régime: Trend Following (momentum)")

        charm_total = exposure_df['charm'].sum()
        print(f"   Total charm exposure: {charm_total:.2f}")
        if charm_total > 0:
            print("   → Flux horaires: Achats mécaniques possibles")
        else:
            print("   → Flux horaires: Ventes mécaniques possibles")

    print()
    print("✅ Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    demo_analysis()