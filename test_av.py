from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.options import Options
import time

API_KEY = 'A85Z12K4YSI3BC5D'

def test_symbol(symbol):
    print(f"Testing {symbol}...")
    try:
        ts = TimeSeries(key=API_KEY)
        data, _ = ts.get_quote_endpoint(symbol=symbol)
        print(f"Price for {symbol}: {data}")
    except Exception as e:
        print(f"Error for {symbol}: {e}")
    
    time.sleep(2)
    
    try:
        opt = Options(key=API_KEY)
        data, _ = opt.get_realtime_options(symbol=symbol)
        print(f"Options for {symbol}: {len(data)} rows")
        if len(data) > 0:
            print(data.head())
    except Exception as e:
        print(f"Error options for {symbol}: {e}")

test_symbol('^SPX')
time.sleep(2)
test_symbol('SPY')
