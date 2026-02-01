import requests
import json
import time

API_KEY = 'A85Z12K4YSI3BC5D'

def check_av(symbol):
    print(f"--- Checking {symbol} ---")
    url = f'https://www.alphavantage.co/query?function=REALTIME_OPTIONS&symbol={symbol}&apikey={API_KEY}'
    
    for attempt in range(3):
        try:
            r = requests.get(url)
            data = r.json()
            
            if 'Note' in data or 'Information' in data:
                print(f"Rate limited or Info: {data.get('Note', data.get('Information'))}")
                print("Waiting 10 seconds before retry...")
                time.sleep(10)
                continue
                
            if 'data' in data:
                print(f"Success! Found {len(data['data'])} options for {symbol}")
                if len(data['data']) > 0:
                    print("Sample:", data['data'][0])
                return
            else:
                print(f"No 'data' field in response for {symbol}: {data}")
                return
        except Exception as e:
            print(f"Error: {e}")
            return
    print(f"Failed to get data for {symbol} after retries.")

# Be extremely conservative
check_av('IBM') # Test with a known stock
time.sleep(5)
check_av('SPX') # The target
time.sleep(5)
check_av('SPY') # ETF alternative

