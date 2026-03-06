import os
import httpx
from dotenv import load_dotenv

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")

def test_login_no_remember():
    url = "https://api.tastyworks.com/sessions"
    payload = {
        "login": USERNAME,
        "password": PASSWORD,
        "remember-me": False
    }
    
    print(f"Attempting login to {url} with remember-me=False...")
    try:
        r = httpx.post(url, json=payload, timeout=10)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 201:
            data = r.json().get('data', {})
            print("Login Successful!")
            print("Keys available:", list(data.keys()))
        else:
            print("Login Failed:", r.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        print("Please set TASTY_USERNAME and TASTY_PASSWORD in .env")
    else:
        test_login_no_remember()
