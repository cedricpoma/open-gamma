import os
import httpx
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")

def test_login_with_user_agent():
    url = "https://api.tastyworks.com/sessions"
    payload = {
        "login": USERNAME,
        "password": PASSWORD,
        "remember-me": True
    }
    
    # Add a real-looking User-Agent
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"Attempting login to {url}...")
    print(f"Headers: {headers}")
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 201:
            data = r.json().get('data', {})
            print("Login Successful!")
            print("Keys available:", list(data.keys()))
        else:
            print("Login Failed:", r.text)
            print("Response Headers:", r.headers)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set TASTY_USERNAME and TASTY_PASSWORD in .env")
    else:
        test_login_with_user_agent()
