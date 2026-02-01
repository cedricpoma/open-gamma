import os
import httpx
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")

def test_legacy_login():
    url = "https://api.tastyworks.com/sessions"
    payload = {
        "login": USERNAME,
        "password": PASSWORD,
        "remember-me": True
    }
    
    print(f"Attempting legacy login to {url}...")
    try:
        r = httpx.post(url, json=payload, timeout=10)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 201:
            data = r.json().get('data', {})
            print("Login Successful!")
            print("Keys available:", list(data.keys()))
            
            if 'dxlink-url' in data:
                print(f"DXLink URL found: {data['dxlink-url']}")
            if 'streamer-url' in data:
                 print(f"Streamer URL found: {data['streamer-url']}")
            if 'session-token' in data:
                print("Session Token found.")
        else:
            print("Login Failed:", r.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set TASTY_USERNAME and TASTY_PASSWORD in .env")
    else:
        test_legacy_login()
