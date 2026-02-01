import argparse
import sys
import os
from gamma_engine import GammaEngine

def main():
    parser = argparse.ArgumentParser(description='SPX Gamma Exposure Analysis Tool')
    parser.add_argument('--csv', type=str, default='data/parquet_spx/spx_quotedata.csv',
                        help='Path to CBOE Quotedata CSV file')
    parser.add_argument('--output', type=str, default='results/gamma_profile.png',
                        help='Output path for the profile plot')
    parser.add_argument('--range', type=float, default=0.1,
                        help='Price range percentage for profile (default 0.1 for +/- 10%%)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print(" SPX Options Gamma Analysis Tool (CBOE Data Version)")
    print("=" * 60)
    
    if not os.path.exists(args.csv):
        print(f"[ERROR] CSV file not found: {args.csv}")
        return 1
        
    engine = GammaEngine()
    
    try:
        # 1. Load data
        engine.load_cboe_csv(args.csv)
        print(f"[INFO] Analysis Date: {engine.data_date}")
        print(f"[INFO] Current Spot: ${engine.spot_price:.2f}")
        
        # 2. Calculate Spot GEX
        spot_gex = engine.calculate_spot_gex()
        print(f"[INFO] Total Spot GEX: ${spot_gex/1e9:.2f} Billion")
        
        # 3. Calculate Profile
        print(f"[INFO] Calculating GEX profile (+/- {args.range*100:.0f}%)...")
        levels, profile = engine.get_gamma_profile(price_range_pct=args.range)
        
        # 4. Find Zero Gamma
        zero_gamma = engine.find_zero_gamma(levels, profile)
        if zero_gamma:
            print(f"[INFO] Zero Gamma Level: {zero_gamma:.2f}")
            dist_pct = (engine.spot_price / zero_gamma - 1) * 100
            print(f"[INFO] Spot is {dist_pct:+.2f}% from Zero Gamma")
        else:
            print("[WARN] Zero Gamma level not found in selected range.")
            
        # 5. Plots
        static_path = engine.plot_profile(levels, profile, zero_gamma, output_path=args.output)
        print(f"[SUCCESS] Static Profile saved to: {static_path}")
        
        interactive_path = engine.plot_interactive_dashboard(levels, profile, zero_gamma)
        print(f"[SUCCESS] Interactive Dashboard saved to: {interactive_path}")
        
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"[ERROR] An error occurred: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())