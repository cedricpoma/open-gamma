import os
import httpx
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")
CLIENT_ID = os.getenv("TASTY_CLIENT_ID")
CLIENT_SECRET = os.getenv("TASTY_CLIENT_SECRET")

def test_oauth_password_flow():
    url = "https://api.tastyworks.com/oauth/token"
    # Try password grant
    payload = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": USERNAME,
        "password": PASSWORD,
        "scope": "orders:read orders:write" # Usually implied or specific
    }
    
    print(f"[DEBUG] Attempting OAuth Password Grant to {url}...")
    try:
        r = httpx.post(url, json=payload, timeout=10)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_oauth_password_flow()
