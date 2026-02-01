# SPX Options Gamma Analysis Tool (CBOE Data Version)

This tool calculates and visualizes **Gamma Exposure (GEX)** and the **Zero Gamma Level** for SPX options, following the methodology described by Perfiliev.

## Methodology
The tool uses the following formula for Gamma Exposure:
`GEX = Option's Gamma * Contract Size * Open Interest * Spot Price^2 * 0.01`

- **Long Calls** contribute positive gamma.
- **Short Puts** (Market Maker perspective) contribute negative gamma.
- **Zero Gamma Level**: The price point where total dealer gamma flips from positive to negative.

## Data Source
The tool is designed to work with **CBOE Quotedata CSV** files. 
1. Go to [CBOE Delayed Quotes](https://www.cboe.com/delayed_quotes/spx)
2. Select "All" for Options Range and Expiration.
3. Click "Download CSV" at the bottom.
4. Place the file in `data/parquet_spx/spx_quotedata.csv`.

## Installation
Ensure you have the dependencies installed:
```bash
pip install pandas numpy scipy matplotlib
```

## Usage
Run the analysis with:
```powershell
.\venv\Scripts\python.exe main.py
```

### Options:
- `--csv`: Path to your CBOE CSV file (default: `data/parquet_spx/spx_quotedata.csv`)
- `--output`: Path to save the profile plot (default: `results/gamma_profile.png`)
- `--range`: Price range percentage for the profile (default: `0.1` for +/- 10%)

## Results
- **Current Spot GEX**: Total dollar value of delta-hedging flow per 1% move.
- **Zero Gamma Level**: Critical support/resistance level where market volatility regime changes.
- **Gamma Profile Plot**: Visual representation of dealer positioning across price levels.

---
*Based on the methodology from [Perfiliev's Blog](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)*