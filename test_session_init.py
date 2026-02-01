import os
import httpx
from dotenv import load_dotenv
from tastytrade import Session

load_dotenv()
USERNAME = os.getenv("TASTY_USERNAME")
PASSWORD = os.getenv("TASTY_PASSWORD")
CLIENT_ID = os.getenv("TASTY_CLIENT_ID")
CLIENT_SECRET = os.getenv("TASTY_CLIENT_SECRET")

def get_remember_token():
    url = "https://api.tastyworks.com/sessions"
    payload = {
        "login": USERNAME,
        "password": PASSWORD,
        "remember-me": True
    }
    
    print(f"[DEBUG] Fetching remember-token from {url}...")
    r = httpx.post(url, json=payload, timeout=10)
    if r.status_code == 201:
        data = r.json().get('data', {})
        token = data.get('remember-token')
        print(f"[DEBUG] Token received: {token[:10]}...")
        return token
    else:
        print(f"[ERROR] Login failed: {r.text}")
        return None

def test_session():
    token = get_remember_token()
    if not token:
        return

    print("-" * 30)
    print("Testing Session with CLIENT_SECRET...")
    try:
        # Note: Session expects provider_secret first
        session = Session(CLIENT_SECRET, token)
        print("[SUCCESS] Session created with CLIENT_SECRET!")
        print(f"Is Valid? {session.validate()}")
        return
    except Exception as e:
        print(f"[FAIL] Session with SECRET failed: {e}")

    print("-" * 30)
    print("Testing Session with EMPTY Secret (Legacy mode?)...")
    try:
        session = Session("", token)
        print("[SUCCESS] Session created with EMPTY SECRET!")
        print(f"Is Valid? {session.validate()}")
        return
    except Exception as e:
        print(f"[FAIL] Session with EMPTY SECRET failed: {e}")

if __name__ == "__main__":
    test_session()
